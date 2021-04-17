import sys
from TwoRRProblem import read_instance
from TwoRRMaster import solve_master

if __name__=="__main__":
    filename = sys.argv[1]
    prob = read_instance(filename)
    solve_master(filename, prob, True)
