# This file contains the "slave" part of the master-slave
# algorithm. Given a home-away pattern (computed in the master)
# the slave creates the assignments between teams. Note that,
# given a certain home-away pattern, a feasible assignment
# does not necessarily exist.

# pylint: disable=no-name-in-module, no-member

import os
#os.environ["GRB_LICENSE_FILE"] = "C:\\gurobi\\gurobi-ac.lic"
import gurobipy as gp
from gurobipy import GRB
from TwoRRProblem import TwoRRProblem, write_solution
from TwoRRValidator import validate_constraint

def solve_slave(prob, model, ha_patterns, debug = True):

    n_teams = len(prob.teams)
    n_slots = len(prob.slots)

    # Fix the variables
    for team1 in range(n_teams):
        for team2 in range(n_teams):
            if team1 == team2:
                continue
            for slot in range(n_slots):
                if ha_patterns[team1][slot] == 0 or ha_patterns[team2][slot] == 1:
                    model._vars[team1, team2, slot].ub = 0
                else:
                    model._vars[team1, team2, slot].ub = 1

    print(">>>> Slave: Finding assignment...")

    # Optimize
    model.optimize()

    write_status(model)

    if (model.solCount > 0):
        solution = make_solution(model._vars, n_teams, n_slots)
        obj = 0
        for constraint in prob.constraints:
            violated,diff,penalty = validate_constraint(prob, solution, constraint)
            obj += penalty
            #print(constraint[0], (violated,diff,penalty))
        if model._best_obj == -1 or obj < model._best_obj:
            model._best_obj = obj
            print(">>>> Slave: Found new best incumbent with value: " + str(obj))
            write_solution("ms_solution.xml", prob, model._vars, model.objVal)
        else:
            print(">>>> Slave: Found assignment with value: " + str(obj))
    
    return False


def create_slave(prob: TwoRRProblem, env, skipSoft=False, lazy=0, debug=True):
    # Set up and solve with Gurobi a "naive" model 
    # for the TwoRRProblem. The model is naive in
    # the sense that il follows the standard integer
    # programming techniques, building a large complex
    # model and hope that Gurobi will be able to handle
    # it. This works only for simple problems.

    n_teams = len(prob.teams)
    n_slots = len(prob.slots)

    # Create Gurobi model
    model = gp.Model(prob.name, env)
    model.setParam("OutputFlag", 0)
    model.setParam("Threads", 1)
    # Tuning parameters
    model.setParam("Presolve", 2)
    model.setParam("Symmetry", 2)
    model.setParam("GomoryPasses", 1)
    model.setParam("PrePasses", 2)

    model.setParam("MIPFocus", 1)
    model.setParam("Heuristics", 0.5)

    model.setParam("TimeLimit", 600)

    model._best_obj = -1

    # Create variables and store them in a dictionary:
    # m_vars[home_team, away_team, slot]
    m_vars = dict()
    model._vars = m_vars
    for team1 in range(n_teams):
        for team2 in range(n_teams):
            if team1 == team2:
                continue
            for slot in range(n_slots):
                m_vars[team1, team2, slot] = \
                    model.addVar(vtype=GRB.BINARY, name="x_" + str(team1) + "_" + str(team2) + "_" + str(slot))

    # Add constraints that force each team to play against
    # another team at most once per slot.
    for team1 in range(n_teams):
            for slot in range(n_slots):
                model.addConstr(gp.quicksum([m_vars[team1, team2, slot] + m_vars[team2, team1, slot]
                                            for team2 in range(n_teams) if team1 != team2]) <= 1)

    # Add constraints that force each team to meet another
    # team exactly once in a home game
    for team1 in range(n_teams):
        for team2 in range(n_teams):
            if team1 == team2:
                continue
            model.addConstr(gp.quicksum([m_vars[team1, team2, slot] for slot in range(n_slots)]) == 1)
    
    # If phased, the teams must play in separate intervals, i.e., once in each
    # n_slots/2 interval.
    if (prob.game_mode == "P"):
        for team1 in range(n_teams):
            for team2 in range(team1 + 1, n_teams):
                model.addConstr(gp.quicksum([m_vars[team1,team2,slot] + m_vars[team2,team1,slot] 
                                            for slot in range(int(n_slots/2))]) <= 1)
                model.addConstr(gp.quicksum([m_vars[team1,team2,slot] + m_vars[team2,team1,slot] 
                                            for slot in range(int(n_slots/2), n_slots)]) <= 1)

    # Add problem specific constraints
    for (ind, (c_name, constraint)) in enumerate(prob.constraints):
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
                        constr = model.addConstr(sepc_var - slack <= - c_min - 1 + n_slots)
                        if lazy:
                            constr.Lazy = lazy
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

                        constr = model.addConstr(min1_var + min2_var == 1, name="SE1_3_" + str(teams[i]) + "_" + str(teams[j]) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy

    return model


def write_status(model: gp.Model):
    # Displays the status of Gurobi in a more human readable format
    if model.status == GRB.OPTIMAL:
        print('>>>> Slave: Optimal objective: %g' % model.objVal)
    elif model.status == GRB.INF_OR_UNBD:
        print('>>>> Slave: Model is infeasible or unbounded')
    elif model.status == GRB.INFEASIBLE:
        print('>>>> Slave: Model is infeasible')
        #model.write("infeasible.lp")
        #raise Exception("Infeasilbe!")
    elif model.status == GRB.UNBOUNDED:
        print('>>>> Slave: Model is unbounded')
    elif model.status == GRB.TIME_LIMIT:
        print('>>>> Slave: Reached time limit')
    else:
        print('>>>> Slave: Optimization ended with status %d' % model.status)


def make_solution(m_vars, n_teams, n_slots):
    # Computes the solution from the binary variables of the model
    solution = []
    for slot in range(n_slots):
        games = []
        for team1 in range(n_teams):
            for team2 in range(n_teams):
                if team1 == team2:
                    continue
                var_value = m_vars[team1, team2, slot]
                if isinstance(var_value, gp.Var):
                    var_value = var_value.x
                if var_value > 0.5:
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