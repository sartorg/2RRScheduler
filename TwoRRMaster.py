# This file contains the various optimization procedures
# for a master of the TwoRRProblem. The master problem
# is tasked with the generation of the home away pattern

# pylint: disable=no-name-in-module, no-member

import os
#os.environ["GRB_LICENSE_FILE"] = "C:\\gurobi\\gurobi-ac.lic"
import gurobipy as gp
from gurobipy import GRB
from TwoRRProblem import TwoRRProblem, write_solution
from TwoRRValidator import validate_constraint

def solve_master(prob: TwoRRProblem, skipSoft=False, lazy=0, debug=True):
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
    model.setParam("Threads", 4)

    if debug:
        print("Creating binary variables...")

    # Create variables and store them in a dictionary:
    # m_vars[t, s] = 1 if team t plays home in slot s, 0 otherwise
    m_vars = dict()
    for team in range(n_teams):
        for slot in range(n_slots):
            m_vars[team, slot] = model.addVar(vtype=GRB.BINARY, name="x_" + str(team) + "_" + str(slot))
    
    # Additional vars that determine whether a team has an away break or a home break
    # in a certain slot.
    bh_vars = dict() # Home breaks
    ba_vars = dict() # Away breaks
    def get_break_var(team, slot, away=False):
        if away:
            if (team, slot) not in ba_vars:
                ba_var = model.addVar(vtype=GRB.BINARY, name="ba_" + str(team) + "_" + str(slot))
                ba_vars[team, slot] = ba_var
                model.addConstr(1 - m_vars[team, slot - 1] - m_vars[team, slot] <= ba_var)
            return ba_vars[team, slot]
        else:
            if (team, slot) not in bh_vars:
                bh_var = model.addVar(vtype=GRB.BINARY, name="bh_" + str(team) + "_" + str(slot))
                bh_vars[team, slot] = bh_var
                model.addConstr(m_vars[team, slot - 1] + m_vars[team, slot] - 1 <= bh_var)
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
                        constr = model.addConstr(len(slots) - gp.quicksum([m_vars[team, slot]
                                            for slot in slots]) <= c_max,
                                        name="CA1_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                    elif constraint["mode"] == "H":
                        constr = model.addConstr(gp.quicksum([m_vars[team, slot]
                                            for slot in slots]) <= c_max,
                                        name="CA1_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                    else:
                        raise Exception("Mode HA for CA1 not implemented!")
                elif not skipSoft:
                    slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
                    if constraint["mode"] == "A":
                        constr = model.addConstr(len(slots) - gp.quicksum([m_vars[team, slot]
                                            for slot in slots]) - slack <= c_max,
                                        name="CA1_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                    elif constraint["mode"] == "H":
                        constr = model.addConstr(gp.quicksum([m_vars[team, slot]
                                            for slot in slots]) - slack <= c_max,
                                        name="CA1_" + str(team) + "_" + str(ind))
                        if lazy:
                            constr.Lazy = lazy
                    else:
                        raise Exception("Mode HA for CA1 not implemented!")

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
                            constr = model.addConstr(gp.quicksum([m_vars[team1,s] 
                                                            for s in range(slot + 1)]) - \
                                            gp.quicksum([m_vars[team2,s] 
                                                            for s in range(slot + 1)]) <= intp,
                                            name="FA2_1_" + str(team1) + "_" + str(team2) + "_" + str(slot) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy
                            constr = model.addConstr(gp.quicksum([m_vars[team2,s] 
                                                            for s in range(slot + 1)]) - \
                                            gp.quicksum([m_vars[team1,s] 
                                                            for s in range(slot + 1)]) <= intp,
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
                        constr = model.addConstr(largest_diff_var - slack <= intp)
                        if lazy:
                                constr.Lazy = lazy
                        for slot in slots:
                            diff_var =  model.addVar(vtype=GRB.INTEGER, name="diff_" + str(team1) + "_" + str(team2) + "_" + str(slot))
                            constr = model.addConstr(gp.quicksum([m_vars[team1,s] 
                                                            for s in range(slot + 1)]) - \
                                            gp.quicksum([m_vars[team2,s] 
                                                            for s in range(slot + 1)]) <= diff_var,
                                            name="FA2_1_" + str(team1) + "_" + str(team2) + "_" + str(slot) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy
                            constr = model.addConstr(gp.quicksum([m_vars[team2,s] 
                                                            for s in range(slot + 1)]) - \
                                            gp.quicksum([m_vars[team1,s] 
                                                            for s in range(slot + 1)]) <= diff_var,
                                            name="FA2_2_" + str(team1) + "_" + str(team2) + "_" + str(slot) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy

                            constr = model.addConstr(diff_var <= largest_diff_var, name="FA2_3_" + str(team1) + "_" + str(team2) + "_" + str(slot) + "_" + str(ind))
                            if lazy:
                                constr.Lazy = lazy
    
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
            x = model.cbGetSolution(m_vars)
            solution = make_solution(x, n_teams, n_slots)
            write_ha_pattern("ha_pattern_{}".format(solcnt), solution)
    
    def write_ha_pattern(file_name, solution):
        with open(file_name, "w") as myfile:
            myfile.write(str(n_teams))
            myfile.write("\n")
            myfile.write(str(n_slots))
            myfile.write("\n")
            for team, pattern in enumerate(solution):
                myfile.write(str(team))
                myfile.write("\n")
                for ha in pattern:
                    myfile.write(str(int(ha)))
                myfile.write("\n")

    # Solution pool
    model.setParam("PoolSolutions", 1)
    model.setParam("PoolSearchMode", 2)
    model.setParam("MIPFocus", 1)
    model.setParam("Heuristics", 0.5)

    # Tuning parameters
    model.setParam("Presolve", 2)
    model.setParam("Symmetry", 2)
    model.setParam("GomoryPasses", 1)
    model.setParam("PrePasses", 2)

    if debug:
        print("Solving...")

    # Optimize
    if skipSoft:
        #model.optimize(callbackGetIncumbent)
        model.optimize()
    else:
        model.optimize(callbackGetIncumbent)

    write_status(model)

    if (model.status == GRB.OPTIMAL):
        solution = make_solution(m_vars, n_teams, n_slots)
        if debug:
            print_solution(solution)
        
    # if (model.status == GRB.OPTIMAL):
    #     write_solution("solution.xml", prob, m_vars, model.objVal)
    
    # obj = 0
    # for constraint in prob.constraints:
    #     violated,diff,penalty = validate_constraint(prob, solution, constraint)
    #     obj += penalty
    #     print(constraint[0], (violated,diff,penalty))
    
    # print("Obj validator: " + str(obj))


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
        ha_pattern = []
        for team in range(n_teams):
            var_value = m_vars[team, slot]
            if isinstance(var_value, gp.Var):
                var_value = var_value.x
            ha_pattern.append(var_value)
        solution.append(ha_pattern)
    return solution

def print_solution(solution):
    # Displays the solution in a more human readble format
    for slot,games in enumerate(solution):
        print("Slot " + str(slot) + ":")
        for ha in games:
            if (ha == 1):
                print("H", end=' ')
            else:
                print("A", end=' ')
        print("")