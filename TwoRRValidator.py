# Validates the constraints of a TwoRRProblem, that is checks
# whether a constraint is violated and by how much.

from TwoRRProblem import TwoRRProblem

def validate_constraint(problem: TwoRRProblem, solution, twoRRConstraint):
    # The solution is, for example, [[(0,1), (2,3)], [(1,0), (3,2)]].
    # Each game is a tuple of team ids. There is a list of games for each slot.
    # The constraint is in the same format used in the RobinX format.

    c_name = twoRRConstraint[0]
    constraint = twoRRConstraint[1]

    n_slots = len(problem.slots)
    n_teams = len(problem.teams)

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
    
    def has_home_break(team, slot, away=False):
        # Checks that a certain team has a home or away break
        # in a certain slot
        for h,a in solution[slot]:
            # Check whether it played away in this slot
            if away and a == team:
                for p_h,p_a in solution[slot - 1]:
                    # Check whether it played away in the previous slot
                    if p_a == team:
                        return True
            # Check whether it played home in this slot
            if not away and h == team:
                for p_h,p_a in solution[slot - 1]:
                    # Check whether it played home in the previous slot
                    if p_h == team:
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
        
        return (diff > 0, diff, penalty * diff)

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
        
        return (diff > 0, diff, penalty * diff)

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
        
        return (diff > 0, diff, penalty * diff)
            
    if c_name == "CA4":
        slots = [int(s) for s in constraint["slots"].split(';')]
        teams1 = [int(t) for t in constraint["teams1"].split(';')]
        teams2 = [int(t) for t in constraint["teams2"].split(';')]
        c_min = int(constraint["min"])
        c_max = int(constraint["max"])
        penalty = int(constraint["penalty"])
        if (c_min > 0):
            raise Exception("Min value in CA4 not implemented!")
        if constraint["mode1"] == "A":
            if constraint["mode2"] == "GLOBAL":
                diff += max(sum([plays_home_against(i, j, z, away=True) 
                                    for i in teams1
                                    for j in teams2 if i != j
                                    for z in slots]) - c_max, 0)
            else:
                for slot in slots:
                    diff += max(sum([plays_home_against(i, j, slot, away=True) 
                                        for i in teams1
                                        for j in teams2 if i != j]) - c_max, 0)
        elif constraint["mode1"] == "H":
            if constraint["mode2"] == "GLOBAL":
                diff += max(sum([plays_home_against(i, j, z) 
                                    for i in teams1
                                    for j in teams2 if i != j
                                    for z in slots]) - c_max, 0)
            else:
                for slot in slots:
                    diff += max(sum([plays_home_against(i, j, slot) 
                                        for i in teams1
                                        for j in teams2 if i != j]) - c_max, 0)
        else:
            if constraint["mode2"] == "GLOBAL":
                diff += max(sum([plays_home_against(i, j, z, away=True) 
                                    for i in teams1
                                    for j in teams2 if i != j
                                    for z in slots])  + 
                            sum([plays_home_against(i, j, z) 
                                    for i in teams1
                                    for j in teams2 if i != j
                                    for z in slots]) - c_max, 0)
            else:
                for slot in slots:
                    diff += max(sum([plays_home_against(i, j, slot, away=True) 
                                        for i in teams1
                                        for j in teams2 if i != j]) +
                                sum([plays_home_against(i, j, slot) 
                                        for i in teams1
                                        for j in teams2 if i != j]) - c_max, 0)
        
        return (diff > 0, diff, penalty * diff)

    # Game constraints
    if c_name == "GA1":
        slots = [int(s) for s in constraint["slots"].split(';')]
        games = [(int(t.split(',')[0]),int(t.split(',')[1])) for t in constraint["meetings"].split(';') if len(t) > 0]
        c_min = int(constraint["min"])
        c_max = int(constraint["max"])
        penalty = int(constraint["penalty"])
        diff += max(sum([plays_home_against(i, j, slot) 
                        for i,j in games
                        for slot in slots]) - c_max, 0)
        diff += max(c_min - sum([plays_home_against(i, j, slot) 
                                for i,j in games
                                for slot in slots]), 0)
        
        return (diff > 0, diff, penalty * diff)

    # Break constraints
    if c_name == "BR1":
        teams = [int(t) for t in constraint["teams"].split(';')]
        slots = [int(s) for s in constraint["slots"].split(';')]
        mode = constraint["mode2"]
        intp = int(constraint["intp"])
        penalty = int(constraint["penalty"])
        if mode == "A":
            for team in teams:
                diff += max(sum([has_home_break(team, slot, away=True) 
                                    for slot in slots if slot != 0]) - intp, 0)
            for team in teams:
                diff += max(sum([has_home_break(team, slot, away=False) 
                                    for slot in slots if slot != 0]) - intp, 0)
        else:
            for team in teams:
                diff += max(sum([has_home_break(team, slot, away=False) 
                                    for slot in slots if slot != 0]) + 
                            sum([has_home_break(team, slot, away=True) 
                                    for slot in slots if slot != 0]) - intp, 0)
        
        return (diff > 0, diff, penalty * diff)

    if c_name == "BR2":
        teams = [int(t) for t in constraint["teams"].split(';')]
        slots = [int(s) for s in constraint["slots"].split(';')]
        intp = int(constraint["intp"])
        penalty = int(constraint["penalty"])
        diff += max(sum([has_home_break(team, slot, away=False) + has_home_break(team, slot, away=True)
                            for team in teams
                            for slot in slots if slot != 0]) - intp, 0)
        
        return (diff > 0, diff, penalty * diff)

    # Fairness constraints
    if c_name == "FA2":
        teams = [int(t) for t in constraint["teams"].split(';')]
        slots = sorted([int(s) for s in constraint["slots"].split(';')])
        intp = int(constraint["intp"])
        penalty = int(constraint["penalty"])
        for team1 in teams:
            for team2 in teams:
                if team1 == team2:
                    continue
                tmp_diff = []
                for slot in slots:
                    tmp_diff.append(max(abs(sum([plays_home_against(team1,i,j) 
                                                for i in range(n_teams) if i != team1
                                                for j in range(slot + 1)]) - 
                                            sum([plays_home_against(team2,i,j)
                                                for i in range(n_teams) if i != team2
                                                for j in range(slot + 1)])) - intp
                                    , 0))
                
                diff += max(tmp_diff)

        return (diff > 0, diff, penalty * diff)
                        
    # Separation constraints
    if c_name == "SE1":
        teams = [int(t) for t in constraint["teams"].split(';')]
        penalty = int(constraint["penalty"])
        c_min = int(constraint["min"])
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                diff += max(c_min + 1 - abs(sum([slot * plays_home_against(teams[i],teams[j],slot) 
                                            for slot in range(n_slots)]) - 
                                        sum([slot * plays_home_against(teams[j],teams[i],slot) 
                                            for slot in range(n_slots)]))
                            , 0)
        
        return (diff > 0, diff, penalty * diff)
