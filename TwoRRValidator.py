# Validates the constraints of a TwoRRProblem, that is checks
# whether a constraint is violated and by how much.

from TwoRRProblem import TwoRRProblem

def validate_constraint(model: TwoRRProblem, solution, c_name, constraint):
    # The solution is, for example, [[(0,1), (2,3)], [(1,0), (3,2)]].
    # Each game is a tuple of team ids. There is a list of games for each slot.
    # The constraint is in the same format used in the RobinX format.

    n_slots = len(model.slots)

    def plays_home(team, slot, away=False):
        # Checks that a certain team plays home or away
        # in a certain slot
        for h,a in solution[slot]:
            if away and a == team:
                return True
            if not away and h == team:
                return True
        return False
    
    def plays_home_against(team, other_team, slot, away=False):
        # Checks that a certain team plays home or away
        # against another team in a certain slot
        for h,a in solution[slot]:
            if away and a == team and h == other_team:
                return True
            if not away and h == team and a == other_team:
                return True
        return False

    diff = 0
    
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
            if constraint["mode"] == "A":
                diff += max(sum([plays_home(team, slot, away=True)
                                    for slot in slots]) - c_max, 0)
            elif constraint["mode"] == "H":
                diff += max(sum([plays_home(team, slot)
                                    for slot in slots]) - c_max, 0)
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
                    diff += max(sum([plays_home_against(team, other_team, slot, away=True)
                                        for other_team in teams2 if other_team != team
                                        for slot in slots]) - c_max, 0)
                elif constraint["mode1"] == "H":
                    diff += max(sum([plays_home_against(team, other_team, slot)
                                        for other_team in teams2 if other_team != team
                                        for slot in slots]) - c_max, 0)
                else:
                    diff += max(sum([plays_home_against(team, other_team, slot, away=True)
                                        for other_team in teams2 if other_team != team
                                        for slot in slots]) + 
                                sum([plays_home_against(team, other_team, slot)
                                        for other_team in teams2 if other_team != team
                                        for slot in slots]) - c_max, 0)

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
                        diff += max(sum([plays_home_against(team, other_team, slot, away=True)
                                        for other_team in teams2 if other_team != team
                                        for slot in slots]) - c_max, 0)
                elif constraint["mode1"] == "H":
                    for slots in [range(z, z + intp) for z in range(n_slots - intp + 1)]:
                        diff += max(sum([plays_home_against(team, other_team, slot)
                                        for other_team in teams2 if other_team != team
                                        for slot in slots]) - c_max, 0)
                else:
                    for slots in [range(z, z + intp) for z in range(n_slots - intp + 1)]:
                        diff += max(sum([plays_home_against(team, other_team, slot, away=True)
                                        for other_team in teams2 if other_team != team
                                        for slot in slots]) + 
                                sum([plays_home_against(team, other_team, slot)
                                        for other_team in teams2 if other_team != team
                                        for slot in slots]) - c_max, 0)
            
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
                    diff += max(sum([plays_home_against(i, j, z, away=True) 
                                        for i in teams2
                                        for j in teams1 if i != j
                                        for z in slots]) - c_max, 0)
                else:
                    for slot in slots:
                        diff += max(sum([plays_home_against(i, j, slot, away=True) 
                                            for i in teams2
                                            for j in teams1 if i != j]) - c_max, 0)
            elif constraint["mode1"] == "H":
                if constraint["mode2"] == "GLOBAL":
                    diff += max(sum([plays_home_against(i, j, z) 
                                        for i in teams2
                                        for j in teams1 if i != j
                                        for z in slots]) - c_max, 0)
                else:
                    for slot in slots:
                        diff += max(sum([plays_home_against(i, j, slot) 
                                            for i in teams2
                                            for j in teams1 if i != j]) - c_max, 0)
            else:
                if constraint["mode2"] == "GLOBAL":
                    diff += max(sum([plays_home_against(i, j, z, away=True) 
                                        for i in teams2
                                        for j in teams1 if i != j
                                        for z in slots])  + 
                                sum([plays_home_against(i, j, z) 
                                        for i in teams2
                                        for j in teams1 if i != j
                                        for z in slots]) - c_max, 0)
                else:
                    for slot in slots:
                        diff += max(sum([plays_home_against(i, j, slot, away=True) 
                                            for i in teams2
                                            for j in teams1 if i != j]) +
                                    sum([plays_home_against(i, j, slot) 
                                            for i in teams2
                                            for j in teams1 if i != j]) - c_max, 0)

    # Game constraints
    # if c_name == "GA1":
    #     slots = [int(s) for s in constraint["slots"].split(';')]
    #     games = [(int(t.split(',')[0]),int(t.split(',')[1])) for t in constraint["meetings"].split(';') if len(t) > 0]
    #     c_min = int(constraint["min"])
    #     c_max = int(constraint["max"])
    #     penalty = int(constraint["penalty"])
    #     if constraint["type"] == "HARD":
    #         model.addConstr(gp.quicksum([m_vars[i, j, slot] 
    #                             for i,j in games
    #                             for slot in slots]) <= c_max,
    #                         name="GA1_max_" + str(slot) + "_" + str(ind))
    #         model.addConstr(gp.quicksum([m_vars[i, j, slot] 
    #                             for i,j in games
    #                             for slot in slots]) >= c_min,
    #                         name="GA1_min_" + str(slot) + "_" + str(ind))
    #     elif not skipSoft:
    #         slack_plus = model.addVar(vtype=GRB.INTEGER, obj=penalty)
    #         model.addConstr(gp.quicksum([m_vars[i, j, slot] 
    #                             for i,j in games
    #                             for slot in slots]) - slack_plus <= c_max,
    #                         name="GA1_max_" + str(slot) + "_" + str(ind))
    #         slack_minus = model.addVar(vtype=GRB.INTEGER, obj=penalty)
    #         model.addConstr(gp.quicksum([m_vars[i, j, slot] 
    #                             for i,j in games
    #                             for slot in slots]) + slack_minus >= c_min,
    #                         name="GA1_min_" + str(slot) + "_" + str(ind))
    # # Break constraints
    # if c_name == "BR1":
    #     teams = [int(t) for t in constraint["teams"].split(';')]
    #     slots = [int(s) for s in constraint["slots"].split(';')]
    #     mode = constraint["mode2"]
    #     intp = int(constraint["intp"])
    #     penalty = int(constraint["penalty"])
    #     if constraint["type"] == "HARD":
    #         if mode == "A":
    #             for team in teams:
    #                 model.addConstr(gp.quicksum([get_break_var(team, slot, away=True) 
    #                                     for slot in slots if slot != 0]) <= intp,
    #                                 name="BR1_" + str(team) + "_" + str(ind))
    #         elif mode == "H":
    #             for team in teams:
    #                 model.addConstr(gp.quicksum([get_break_var(team, slot, away=False) 
    #                                     for slot in slots if slot != 0]) <= intp,
    #                                 name="BR1_" + str(team) + "_" + str(ind))
    #         else:
    #             for team in teams:
    #                 model.addConstr(gp.quicksum([get_break_var(team, slot, away=False) + get_break_var(team, slot, away=True)
    #                                     for slot in slots if slot != 0]) <= intp,
    #                                 name="BR1_" + str(team) + "_" + str(ind))
    #     elif not skipSoft:
    #         if mode == "A":
    #             for team in teams:
    #                 slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
    #                 model.addConstr(gp.quicksum([get_break_var(team, slot, away=True) 
    #                                     for slot in slots if slot != 0]) - slack <= intp,
    #                                 name="BR1_" + str(team) + "_" + str(ind))
    #         elif mode == "H":
    #             for team in teams:
    #                 slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
    #                 model.addConstr(gp.quicksum([get_break_var(team, slot, away=False) 
    #                                     for slot in slots if slot != 0]) - slack <= intp,
    #                                 name="BR1_" + str(team) + "_" + str(ind))
    #         else:
    #             for team in teams:
    #                 slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
    #                 model.addConstr(gp.quicksum([get_break_var(team, slot, away=False) + get_break_var(team, slot, away=True)
    #                                     for slot in slots if slot != 0]) - slack <= intp,
    #                                 name="BR1_" + str(team) + "_" + str(ind))
    # if c_name == "BR2":
    #     teams = [int(t) for t in constraint["teams"].split(';')]
    #     slots = [int(s) for s in constraint["slots"].split(';')]
    #     intp = int(constraint["intp"])
    #     penalty = int(constraint["penalty"])
    #     if constraint["type"] == "HARD":
    #         model.addConstr(gp.quicksum([get_break_var(team, slot, away=False) + get_break_var(team, slot, away=True)
    #                             for team in teams
    #                             for slot in slots if slot != 0]) <= intp,
    #                         name="BR2_" + str(ind))
    #     elif not skipSoft:
    #         slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
    #         model.addConstr(gp.quicksum([get_break_var(team, slot, away=False) + get_break_var(team, slot, away=True)
    #                             for team in teams
    #                             for slot in slots if slot != 0]) - slack <= intp,
    #                         name="BR2_" + str(ind))
    # # Fairness constraints
    # if c_name == "FA2":
    #     teams = [int(t) for t in constraint["teams"].split(';')]
    #     slots = sorted([int(s) for s in constraint["slots"].split(';')])
    #     intp = int(constraint["intp"])
    #     penalty = int(constraint["penalty"])
    #     if constraint["type"] == "HARD":
    #         for team1 in teams:
    #             for team2 in teams:
    #                 if team1 == team2:
    #                     continue
    #                 for slot in slots:
    #                     model.addConstr(gp.quicksum([m_vars[team1,i,j] 
    #                                                     for i in range(n_teams) if i != team1
    #                                                     for j in range(slot + 1)]) - \
    #                                     gp.quicksum([m_vars[team2,i,j] 
    #                                                     for i in range(n_teams) if i != team2
    #                                                     for j in range(slot + 1)]) <= intp,
    #                                     name="FA2_1_" + str(team1) + "_" + str(team2) + "_" + str(slot) + "_" + str(ind))
    #                     model.addConstr(gp.quicksum([m_vars[team2,i,j] 
    #                                                     for i in range(n_teams) if i != team1
    #                                                     for j in range(slot + 1)]) - \
    #                                     gp.quicksum([m_vars[team1,i,j] 
    #                                                     for i in range(n_teams) if i != team2
    #                                                     for j in range(slot + 1)]) <= intp,
    #                                     name="FA2_2_" + str(team1) + "_" + str(team2) + "_" + str(slot) + "_" + str(ind))
    #     elif not skipSoft:
    #         for team1 in teams:
    #             for team2 in teams:
    #                 if team1 == team2:
    #                     continue
    #                 largest_diff_var =  model.addVar(vtype=GRB.INTEGER, name="ldiff_" + str(team1) + "_" + str(team2))
    #                 slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
    #                 model.addConstr(largest_diff_var - slack <= intp)
    #                 for slot in slots:
    #                     diff_var =  model.addVar(vtype=GRB.INTEGER, name="diff_" + str(team1) + "_" + str(team2) + "_" + str(slot))
    #                     model.addConstr(gp.quicksum([m_vars[team1,i,j] 
    #                                                     for i in range(n_teams) if i != team1
    #                                                     for j in range(slot + 1)]) - \
    #                                     gp.quicksum([m_vars[team2,i,j] 
    #                                                     for i in range(n_teams) if i != team2
    #                                                     for j in range(slot + 1)]) <= diff_var,
    #                                     name="FA2_1_" + str(team1) + "_" + str(team2) + "_" + str(slot) + "_" + str(ind))
    #                     model.addConstr(gp.quicksum([m_vars[team2,i,j] 
    #                                                     for i in range(n_teams) if i != team2
    #                                                     for j in range(slot + 1)]) - \
    #                                     gp.quicksum([m_vars[team1,i,j] 
    #                                                     for i in range(n_teams) if i != team1
    #                                                     for j in range(slot + 1)]) <= diff_var,
    #                                     name="FA2_2_" + str(team1) + "_" + str(team2) + "_" + str(slot) + "_" + str(ind))
    #                     model.addConstr(diff_var <= largest_diff_var, name="FA2_3_" + str(team1) + "_" + str(team2) + "_" + str(slot) + "_" + str(ind))
                        
    # # Separation constraints
    # if c_name == "SE1":
    #     teams = [int(t) for t in constraint["teams"].split(';')]
    #     penalty = int(constraint["penalty"])
    #     c_min = int(constraint["min"])
    #     if constraint["type"] == "HARD": 
    #         raise Exception("The HARD version of constraint SE1 is not implemented!")
    #     elif not skipSoft:
    #         for i in range(len(teams)):
    #             for j in range(i + 1, len(teams)):
    #                 sepc_var =  model.addVar(vtype=GRB.INTEGER, name="sep_" + str(teams[i]) + "_" + str(teams[j]))
    #                 min1_var =  model.addVar(vtype=GRB.BINARY, name="min1_" + str(teams[i]) + "_" + str(teams[j]))
    #                 min2_var =  model.addVar(vtype=GRB.BINARY, name="min2_" + str(teams[i]) + "_" + str(teams[j]))
    #                 slack = model.addVar(vtype=GRB.INTEGER, obj=penalty)
    #                 model.addConstr(sepc_var - slack <= - c_min - 1 + n_slots)
    #                 model.addConstr(gp.quicksum([slot * m_vars[teams[i],teams[j],slot] 
    #                                                 for slot in range(n_slots)]) - \
    #                                 gp.quicksum([slot * m_vars[teams[j],teams[i],slot] 
    #                                                 for slot in range(n_slots)]) + n_slots <= sepc_var + min1_var * 2 * n_slots,
    #                                 name="SE1_1_" + str(teams[i]) + "_" + str(teams[j]) + "_" + str(ind)) 
    #                 model.addConstr(gp.quicksum([slot * m_vars[teams[j],teams[i],slot] 
    #                                                 for slot in range(n_slots)]) - \
    #                                 gp.quicksum([slot * m_vars[teams[i],teams[j],slot] 
    #                                                 for slot in range(n_slots)]) + n_slots <= sepc_var + min2_var * 2 * n_slots,
    #                                 name="SE1_2_" + str(teams[i]) + "_" + str(teams[j]) + "_" + str(ind))
    #                 model.addConstr(min1_var + min2_var == 1, name="SE1_3_" + str(teams[i]) + "_" + str(teams[j]) + "_" + str(ind))

    return (diff > 0, diff, penalty * diff)
