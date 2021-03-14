# This file contains the various optimization procedures
# for a TwoRRProblem.

# pylint: disable=no-name-in-module, no-member


from TwoRRProblem import TwoRRProblem
import gurobipy as gp
from gurobipy import GRB

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

    # Slack vars
    s_vars = []

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
                    slack = model.addVar(vtype=GRB.INTEGER, name="s" + str(len(s_vars)))
                    s_vars.append((slack, constraint["penalty"]))
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
                    slack = model.addVar(vtype=GRB.INTEGER, name="s" + str(len(s_vars)))
                    s_vars.append((slack, constraint["penalty"]))
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
                    slack = model.addVar(vtype=GRB.INTEGER, name="s" + str(len(s_vars)))
                    s_vars.append((slack, constraint["penalty"]))
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
                        slack = model.addVar(vtype=GRB.INTEGER, name="s" + str(len(s_vars)))
                        s_vars.append((slack, constraint["penalty"]))
                        model.addConstr(gp.quicksum([m_vars[i, j, z] 
                                        for i in teams2
                                        for j in teams1 if i != j
                                        for z in slots]) - slack <= c_max)
                    else:
                        for slot in slots:
                            slack = model.addVar(vtype=GRB.INTEGER, name="s" + str(len(s_vars)))
                            s_vars.append((slack, constraint["penalty"]))
                            model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                        for i in teams2
                                        for j in teams1 if i != j]) - slack <= c_max)
                elif constraint["mode1"] == "H":
                    if constraint["mode2"] == "GLOBAL":
                        slack = model.addVar(vtype=GRB.INTEGER, name="s" + str(len(s_vars)))
                        s_vars.append((slack, constraint["penalty"]))
                        model.addConstr(gp.quicksum([m_vars[i, j, z] 
                                        for i in teams1
                                        for j in teams2 if i != j
                                        for z in slots]) - slack<= c_max)
                    else:
                        for slot in slots:
                            slack = model.addVar(vtype=GRB.INTEGER, name="s" + str(len(s_vars)))
                            s_vars.append((slack, constraint["penalty"]))
                            model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                        for i in teams1
                                        for j in teams2 if i != j]) - slack <= c_max)
                else:
                    if constraint["mode2"] == "GLOBAL":
                        slack = model.addVar(vtype=GRB.INTEGER, name="s" + str(len(s_vars)))
                        s_vars.append((slack, constraint["penalty"]))
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
                            slack = model.addVar(vtype=GRB.INTEGER, name="s" + str(len(s_vars)))
                            s_vars.append((slack, constraint["penalty"]))
                            model.addConstr(gp.quicksum([m_vars[i, j, slot] 
                                        for i in teams1
                                        for j in teams2 if i != j])  + 
                                        gp.quicksum([m_vars[i, j, slot] 
                                        for i in teams2
                                        for j in teams1 if i != j]) - slack <= c_max)
        # Game constraints
        if c_name == "GA1":
            if constraint["type"] == "HARD":
                pass
            else:
                pass
        # Break constraints
        if c_name == "BR1":
            if constraint["type"] == "HARD":
                pass
            else:
                pass
        if c_name == "BR2":
            if constraint["type"] == "HARD":
                pass
            else:
                pass
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

    model.setObjective(gp.quicksum([s_vars[i][0]*s_vars[i][1] for i in range(len(s_vars))]))

    model.write("test.lp")

    #model.setParam("OutputFlag", 0)

    if debug:
        print("Solving...")
    model.optimize()

    write_status(model)

    if (debug and model.status == GRB.OPTIMAL):
        print_solution(m_vars, n_teams, n_slots)


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
        

    

