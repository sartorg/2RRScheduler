# from TwoRRProblem import read_instance
# from TwoRROptimization import solve_naive
# prob = read_instance("Instances/EarlyInstances/ITC2021_Early_10.xml")
# solve_naive(prob, skipSoft=True, lazy=0)

from TwoRRProblem import read_instance
from TwoRRMaster import solve_master
filename = "Instances/EarlyInstances/ITC2021_Early_2.xml"
prob = read_instance(filename)
solve_master(filename, prob, True)
