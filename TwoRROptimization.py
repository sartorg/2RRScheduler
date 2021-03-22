# This file contains the various optimization procedures
# for a TwoRRProblem.

# pylint: disable=no-name-in-module, no-member

import os
#os.environ["GRB_LICENSE_FILE"] = "C:\\gurobi\\gurobi-ac.lic"
import gurobipy as gp
from gurobipy import GRB
from TwoRRProblem import TwoRRProblem, write_solution
from TwoRRValidator import validate_constraint

def solve_naive(prob: TwoRRProblem, skipSoft=False, lazy=1, debug=True):
    # Set up and solve with Gurobi a "naive" model 
    # for the TwoRRProblem. The model is naive in
    # the sense that il follows the standard integer
    # programming techniques, building a large complex
    # model and hope that Gurobi will be able to handle
    # it. This works only for simple problems.

    if debug:
        print("Solving problem: " + prob.name)

    n_teams = len(prob.teams)
    n_slots = len(prob.slots)

    if debug:
        print("Num. teams: " + str(n_teams))

    # Create Gurobi model
    model = gp.Model(prob.name)
    model.setParam("Threads", 1)

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
    
    # Additional vars that determines weather a team plays home or away in a certain slot.
    ta_vars = dict()
    th_vars = dict()
    def get_team_var(team, slot, away=False):
        if away:
            # Team "team" plays away in slot "slot"
            if (team, slot) not in ta_vars:
                ta_var = model.addVar(vtype=GRB.BINARY, name="ta_" + str(team) + "_" + str(slot))
                ta_vars[team, slot] = ta_var
                model.addConstr(gp.quicksum([m_vars[i,team,slot] 
                                    for i in range(n_teams) if i != team]) <= ta_var)
            return ta_vars[team, slot]
        else:
            # Team "team" plays home in slot "slot"
            if (team, slot) not in th_vars:
                th_var = model.addVar(vtype=GRB.BINARY, name="th_" + str(team) + "_" + str(slot))
                th_vars[team, slot] = th_var
                model.addConstr(gp.quicksum([m_vars[team,i,slot] 
                                    for i in range(n_teams) if i != team]) <= th_var)
            return th_vars[team, slot]
    
    # Additional vars that determine whether a team has an away break or a home break
    # in a certain slot.
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

    if debug:
        print("Adding problem specific constraints...")

    # Add problem specific constraints
    for (ind, (c_name, constraint)) in enumerate(prob.constraints):
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
                        constr = model.addConstr(gp.quicksum([get_team_var(team, slot, away=True) 
                                            for slot in slots]) <= c_max,
                                        name="CA1_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                    elif constraint["mode"] == "H":
                        constr = model.addConstr(gp.quicksum([get_team_var(team, slot, away=False) 
                                            for slot in slots]) <= c_max,
                                        name="CA1_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                    else:
                        raise Exception("Mode HA for CA1 not implemented!")
                elif not skipSoft:
                    slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                    if constraint["mode"] == "A":
                        constr = model.addConstr(gp.quicksum([get_team_var(team, slot, away=True)  
                                            for slot in slots]) - slack <= c_max,
                                        name="CA1_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                    elif constraint["mode"] == "H": 
                        constr = model.addConstr(gp.quicksum([get_team_var(team, slot, away=False) 
                                            for slot in slots]) - slack <= c_max,
                                        name="CA1_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
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
                        constr = model.addConstr(gp.quicksum([m_vars[i, team, j] 
                                            for i in teams2 if i != team
                                            for j in slots]) <= c_max,
                                        name="CA2_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                    elif constraint["mode1"] == "H":
                        constr = model.addConstr(gp.quicksum([m_vars[team, i, j] 
                                            for i in teams2 if i != team
                                            for j in slots]) <= c_max,
                                        name="CA2_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                    else:
                        constr = model.addConstr(gp.quicksum([m_vars[team, i, j] 
                                            for i in teams2 if i != team
                                            for j in slots]) + 
                                        gp.quicksum([m_vars[i, team, j] 
                                            for i in teams2 if i != team
                                            for j in slots]) <= c_max,
                                        name="CA2_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                elif not skipSoft:
                    slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                    if constraint["mode1"] == "A":
                        constr = model.addConstr(gp.quicksum([m_vars[i, team, j] 
                                            for i in teams2 if i != team
                                            for j in slots]) - slack <= c_max,
                                        name="CA2_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                    elif constraint["mode1"] == "H":
                        constr = model.addConstr(gp.quicksum([m_vars[team, i, j] 
                                            for i in teams2 if i != team
                                            for j in slots]) - slack <= c_max,
                                        name="CA2_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                    else:
                        constr = model.addConstr(gp.quicksum([m_vars[team, i, j] 
                                            for i in teams2 if i != team
                                            for j in slots]) + 
                                        gp.quicksum([m_vars[i, team, j] 
                                            for i in teams2 if i != team
                                            for j in slots]) - slack <= c_max,
                                        name="CA2_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
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
                            constr = model.addConstr(gp.quicksum([m_vars[i, team, j] 
                                                for i in teams2 if i != team
                                                for j in slots]) <= c_max,
                                            name="CA3_" + str(team) + "_" + str(slots[0]) + "_" + str(slots[-1]) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy
                    elif constraint["mode1"] == "H":
                        for slots in [range(z, z + intp) for z in range(n_slots - intp + 1)]:
                            constr = model.addConstr(gp.quicksum([m_vars[team, i, j] 
                                                for i in teams2 if i != team
                                                for j in slots]) <= c_max,
                                            name="CA3_" + str(team) + "_" + str(slots[0]) + "_" + str(slots[-1]) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy
                    else:
                        for slots in [range(z, z + intp) for z in range(n_slots - intp + 1)]:
                            constr = model.addConstr(gp.quicksum([m_vars[team, i, j] 
                                                for i in teams2 if i != team
                                                for j in slots]) + 
                                            gp.quicksum([m_vars[i, team, j] 
                                                for i in teams2 if i != team
                                                for j in slots]) <= c_max,
                                            name="CA3_" + str(team) + "_" + str(slots[0]) + "_" + str(slots[-1]) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy
                elif not skipSoft:
                    if constraint["mode1"] == "A":
                        for slots in [range(z, z + intp) for z in range(n_slots - intp + 1)]:
                            slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                            constr = model.addConstr(gp.quicksum([m_vars[i, team, j] 
                                                for i in teams2 if i != team
                                                for j in slots]) - slack <= c_max,
                                            name="CA3_" + str(team) + "_" + str(slots[0]) + "_" + str(slots[-1]) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy
                    elif constraint["mode1"] == "H":
                        for slots in [range(z, z + intp) for z in range(n_slots - intp + 1)]:
                            slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                            constr = model.addConstr(gp.quicksum([m_vars[team, i, j] 
                                                for i in teams2 if i != team
                                                for j in slots]) - slack <= c_max,
                                            name="CA3_" + str(team) + "_" + str(slots[0]) + "_" + str(slots[-1]) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy
                    else:
                        for slots in [range(z, z + intp) for z in range(n_slots - intp + 1)]:
                            slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                            constr = model.addConstr(gp.quicksum([m_vars[team, i, j] 
                                                for i in teams2 if i != team
                                                for j in slots]) + 
                                            gp.quicksum([m_vars[i, team, j] 
                                                for i in teams2 if i != team
                                                for j in slots]) - slack <= c_max,
                                            name="CA3_" + str(team) + "_" + str(slots[0]) + "_" + str(slots[-1]) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy
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
                        constr = model.addConstr(gp.quicksum([m_vars[i, j, z] 
                                            for i in teams2
                                            for j in teams1 if i != j
                                            for z in slots]) <= c_max,
                                        name="CA4_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                    else:
                        for slot in slots:
                            constr = model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                                for i in teams2
                                                for j in teams1 if i != j]) <= c_max,
                                            name="CA4_" + str(slot) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy
                elif constraint["mode1"] == "H":
                    if constraint["mode2"] == "GLOBAL":
                        constr = model.addConstr(gp.quicksum([m_vars[i, j, z] 
                                            for i in teams1
                                            for j in teams2 if i != j
                                            for z in slots]) <= c_max,
                                        name="CA4_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                    else:
                        for slot in slots:
                            constr = model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                                for i in teams1
                                                for j in teams2 if i != j]) <= c_max,
                                            name="CA4_" + str(slot) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy
                else:
                    if constraint["mode2"] == "GLOBAL":
                        constr = model.addConstr(gp.quicksum([m_vars[i, j, z] 
                                            for i in teams1
                                            for j in teams2 if i != j
                                            for z in slots]) + 
                                        gp.quicksum([m_vars[i, j, z] 
                                            for i in teams2
                                            for j in teams1 if i != j
                                            for z in slots]) <= c_max,
                                        name="CA4_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                    else:
                        for slot in slots:
                            constr = model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                                for i in teams1
                                                for j in teams2 if i != j])  + 
                                            gp.quicksum([m_vars[i, j, slot] 
                                                for i in teams2
                                                for j in teams1 if i != j]) <= c_max,
                                            name="CA4_" + str(slot) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy
            elif not skipSoft:
                if constraint["mode1"] == "A":
                    if constraint["mode2"] == "GLOBAL":
                        slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                        constr = model.addConstr(gp.quicksum([m_vars[i, j, z] 
                                            for i in teams2
                                            for j in teams1 if i != j
                                            for z in slots]) - slack <= c_max,
                                        name="CA4_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                    else:
                        for slot in slots:
                            slack = model.addVar(vtype=GRB.INTEGER, obj=penalty, name="sCA4_" + str(slot) + "_" + str(ind))
                            constr = model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                                for i in teams2
                                                for j in teams1 if i != j]) - slack <= c_max,
                                            name="CA4_" + str(slot) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy
                elif constraint["mode1"] == "H":
                    if constraint["mode2"] == "GLOBAL":
                        slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                        constr = model.addConstr(gp.quicksum([m_vars[i, j, z] 
                                            for i in teams1
                                            for j in teams2 if i != j
                                            for z in slots]) - slack<= c_max,
                                        name="CA4_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                    else:
                        for slot in slots:
                            slack = model.addVar(vtype=GRB.INTEGER, obj=penalty, name="sCA4_" + str(slot) + "_" + str(ind))
                            constr = model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                                for i in teams1
                                                for j in teams2 if i != j]) - slack <= c_max,
                                            name="CA4_" + str(slot) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy
                else:  
                    if constraint["mode2"] == "GLOBAL":
                        slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                        constr = model.addConstr(gp.quicksum([m_vars[i, j, z] 
                                            for i in teams1
                                            for j in teams2 if i != j
                                            for z in slots]) + 
                                            gp.quicksum([m_vars[i, j, z] 
                                            for i in teams2
                                            for j in teams1 if i != j
                                            for z in slots]) - slack <= c_max,
                                        name="CA4_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                    else:
                        for slot in slots:
                            slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                            constr = model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                                for i in teams1
                                                for j in teams2 if i != j])  + 
                                                gp.quicksum([m_vars[i, j, slot] 
                                                for i in teams2
                                                for j in teams1 if i != j]) - slack <= c_max,
                                            name="CA4_" + str(slot) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy
        # Game constraints
        if c_name == "GA1":
            slots = [int(s) for s in constraint["slots"].split(';')]
            games = [(int(t.split(',')[0]),int(t.split(',')[1])) for t in constraint["meetings"].split(';') if len(t) > 0]
            c_min = int(constraint["min"])
            c_max = int(constraint["max"])
            penalty = int(constraint["penalty"])
            if constraint["type"] == "HARD":
                constr = model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                    for i,j in games
                                    for slot in slots]) <= c_max,
                                name="GA1_max_" + str(slot) + "_" + str(ind))
                if lazy:
                    constr.Lazy = lazy
                constr = model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                    for i,j in games
                                    for slot in slots]) >= c_min,
                                name="GA1_min_" + str(slot) + "_" + str(ind))
                if lazy:
                    constr.Lazy = lazy
            elif not skipSoft:
                slack_plus = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                constr = model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                    for i,j in games
                                    for slot in slots]) - slack_plus <= c_max,
                                name="GA1_max_" + str(slot) + "_" + str(ind))
                if lazy:
                    constr.Lazy = lazy
                slack_minus = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                constr = model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                    for i,j in games
                                    for slot in slots]) + slack_minus >= c_min,
                                name="GA1_min_" + str(slot) + "_" + str(ind))
                if lazy:
                    constr.Lazy = lazy
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
                        constr = model.addConstr(gp.quicksum([get_break_var(team, slot, away=True) 
                                            for slot in slots if slot != 0]) <= intp,
                                        name="BR1_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                elif mode == "H":
                    for team in teams:
                        constr = model.addConstr(gp.quicksum([get_break_var(team, slot, away=False) 
                                            for slot in slots if slot != 0]) <= intp,
                                        name="BR1_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                else:
                    for team in teams:
                        constr = model.addConstr(gp.quicksum([get_break_var(team, slot, away=False) + get_break_var(team, slot, away=True)
                                            for slot in slots if slot != 0]) <= intp,
                                        name="BR1_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
            elif not skipSoft:
                if mode == "A":
                    for team in teams:
                        slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                        constr = model.addConstr(gp.quicksum([get_break_var(team, slot, away=True) 
                                            for slot in slots if slot != 0]) - slack <= intp,
                                        name="BR1_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                elif mode == "H":
                    for team in teams:
                        slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                        constr = model.addConstr(gp.quicksum([get_break_var(team, slot, away=False) 
                                            for slot in slots if slot != 0]) - slack <= intp,
                                        name="BR1_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                else:
                    for team in teams:
                        slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                        constr = model.addConstr(gp.quicksum([get_break_var(team, slot, away=False) + get_break_var(team, slot, away=True)
                                            for slot in slots if slot != 0]) - slack <= intp,
                                        name="BR1_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
        if c_name == "BR2":
            teams = [int(t) for t in constraint["teams"].split(';')]
            slots = [int(s) for s in constraint["slots"].split(';')]
            intp = int(constraint["intp"])
            penalty = int(constraint["penalty"])
            if constraint["type"] == "HARD":
                constr = model.addConstr(gp.quicksum([get_break_var(team, slot, away=False) + get_break_var(team, slot, away=True)
                                    for team in teams
                                    for slot in slots if slot != 0]) <= intp,
                                name="BR2_" + str(ind))
                if lazy:
                    constr.Lazy = lazy
            elif not skipSoft:
                slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                constr = model.addConstr(gp.quicksum([get_break_var(team, slot, away=False) + get_break_var(team, slot, away=True)
                                    for team in teams
                                    for slot in slots if slot != 0]) - slack <= intp,
                                name="BR2_" + str(ind))
                if lazy:
                    constr.Lazy = lazy
        # Fairness constraints
        if c_name == "FA2":
            teams = [int(t) for t in constraint["teams"].split(';')]
            slots = sorted([int(s) for s in constraint["slots"].split(';')])
            intp = int(constraint["intp"])
            penalty = int(constraint["penalty"])
            if constraint["type"] == "HARD":
                for team1 in teams:
                    for team2 in teams:
                        if team1 == team2:
                            continue
                        for slot in slots:
                            constr = model.addConstr(gp.quicksum([m_vars[team1,i,j] 
                                                            for i in range(n_teams) if i != team1
                                                            for j in range(slot + 1)]) - \
                                            gp.quicksum([m_vars[team2,i,j] 
                                                            for i in range(n_teams) if i != team2
                                                            for j in range(slot + 1)]) <= intp,
                                            name="FA2_1_" + str(team1) + "_" + str(team2) + "_" + str(slot) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy
                            constr = model.addConstr(gp.quicksum([m_vars[team2,i,j] 
                                                            for i in range(n_teams) if i != team1
                                                            for j in range(slot + 1)]) - \
                                            gp.quicksum([m_vars[team1,i,j] 
                                                            for i in range(n_teams) if i != team2
                                                            for j in range(slot + 1)]) <= intp,
                                            name="FA2_2_" + str(team1) + "_" + str(team2) + "_" + str(slot) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy
            elif not skipSoft:
                for team1 in teams:
                    for team2 in teams:
                        if team1 == team2:
                            continue
                        largest_diff_var =  model.addVar(vtype=GRB.INTEGER, name="ldiff_" + str(team1) + "_" + str(team2))
                        slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                        model.addConstr(largest_diff_var - slack <= intp)
                        for slot in slots:
                            diff_var =  model.addVar(vtype=GRB.INTEGER, name="diff_" + str(team1) + "_" + str(team2) + "_" + str(slot))
                            constr = model.addConstr(gp.quicksum([m_vars[team1,i,j] 
                                                            for i in range(n_teams) if i != team1
                                                            for j in range(slot + 1)]) - \
                                            gp.quicksum([m_vars[team2,i,j] 
                                                            for i in range(n_teams) if i != team2
                                                            for j in range(slot + 1)]) <= diff_var,
                                            name="FA2_1_" + str(team1) + "_" + str(team2) + "_" + str(slot) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy
                            constr = model.addConstr(gp.quicksum([m_vars[team2,i,j] 
                                                            for i in range(n_teams) if i != team2
                                                            for j in range(slot + 1)]) - \
                                            gp.quicksum([m_vars[team1,i,j] 
                                                            for i in range(n_teams) if i != team1
                                                            for j in range(slot + 1)]) <= diff_var,
                                            name="FA2_2_" + str(team1) + "_" + str(team2) + "_" + str(slot) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy

                            model.addConstr(diff_var <= largest_diff_var, name="FA2_3_" + str(team1) + "_" + str(team2) + "_" + str(slot) + "_" + str(ind))
                            
        # Separation constraints
        if c_name == "SE1":
            teams = [int(t) for t in constraint["teams"].split(';')]
            penalty = int(constraint["penalty"])
            c_min = int(constraint["min"])
            if constraint["type"] == "HARD": 
                raise Exception("The HARD version of constraint SE1 is not implemented!")
            elif not skipSoft:
                for i in range(len(teams)):
                    for j in range(i + 1, len(teams)):
                        sepc_var =  model.addVar(vtype=GRB.INTEGER, name="sep_" + str(teams[i]) + "_" + str(teams[j]))
                        min1_var =  model.addVar(vtype=GRB.BINARY, name="min1_" + str(teams[i]) + "_" + str(teams[j]))
                        min2_var =  model.addVar(vtype=GRB.BINARY, name="min2_" + str(teams[i]) + "_" + str(teams[j]))
                        slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                        model.addConstr(sepc_var - slack <= - c_min - 1 + n_slots)
                        constr = model.addConstr(gp.quicksum([slot * m_vars[teams[i],teams[j],slot] 
                                                        for slot in range(n_slots)]) - \
                                        gp.quicksum([slot * m_vars[teams[j],teams[i],slot] 
                                                        for slot in range(n_slots)]) + n_slots <= sepc_var + min1_var * 2 * n_slots,
                                        name="SE1_1_" + str(teams[i]) + "_" + str(teams[j]) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                        constr = model.addConstr(gp.quicksum([slot * m_vars[teams[j],teams[i],slot] 
                                                        for slot in range(n_slots)]) - \
                                        gp.quicksum([slot * m_vars[teams[i],teams[j],slot] 
                                                        for slot in range(n_slots)]) + n_slots <= sepc_var + min2_var * 2 * n_slots,
                                        name="SE1_2_" + str(teams[i]) + "_" + str(teams[j]) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy

                        model.addConstr(min1_var + min2_var == 1, name="SE1_3_" + str(teams[i]) + "_" + str(teams[j]) + "_" + str(ind))
    
    if debug:
        model.update()
        print("Num vars: " + str(model.NumVars))
        print("Num constraints: " + str(model.NumConstrs))

    if debug:
        print("Writing problem to file...")
        model.write("problem.lp")

    #model.setParam("OutputFlag", 0)

    # Setting up callback function to retrieve feasible solutions
    def callbackGetIncumbent(model, where):
        if where == GRB.Callback.MIPSOL:
            solcnt = model.cbGet(GRB.Callback.MIPSOL_SOLCNT)
            obj = model.cbGet(GRB.Callback.MIPSOL_OBJ)
            x = model.cbGetSolution(m_vars)
            write_solution("solution_{}.xml".format(solcnt), prob, x, obj)

    # Solution pool
    #model.setParam("PoolSolutions", 100)
    #model.setParam("PoolSearchMode", 2)
    #model.setParam("MIPFocus", 1)
    #model.setParam("Heuristics", 0.5)

    # Tuning parameters
    model.setParam("Presolve", 2)
    model.setParam("Symmetry", 2)
    model.setParam("GomoryPasses", 1)
    model.setParam("PrePasses", 2)

    if debug:
        print("Solving...")

    # Optimize    
    #model.optimize(callbackGetIncumbent)
    model.optimize()

    write_status(model)

    if (model.status == GRB.OPTIMAL):
        solution = make_solution(m_vars, n_teams, n_slots)
        if debug:
            print_solution(solution)
        
    if (model.status == GRB.OPTIMAL):
        write_solution("solution.xml", prob, m_vars, model.objVal)
    
    obj = 0
    for constraint in prob.constraints:
        violated,diff,penalty = validate_constraint(prob, solution, constraint)
        obj += penalty
        print(constraint[0], (violated,diff,penalty))
    
    print("Obj validator: " + str(obj))


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


def make_solution(m_vars, n_teams, n_slots):
    # Computes the solution from the binary variables of the model
    solution = []
    for slot in range(n_slots):
        games = []
        for team1 in range(n_teams):
            for team2 in range(n_teams):
                if team1 == team2:
                    continue
                if (m_vars[team1, team2, slot].x > 0.5):
                    games.append((team1, team2))
        solution.append(games)
    return solution

def print_solution(solution):
    # Displays the solution in a more human readble format
    for slot,games in enumerate(solution):
        print("Slot " + str(slot) + ":")
        for h,a in games:
            print("({},{})".format(str(h), str(a)), end=' ')
        print("")