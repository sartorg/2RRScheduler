use itertools::*;
use std::time::{Duration, Instant};
use std::collections::{HashMap, HashSet};
use satcoder::solvers::cadical::{Cadical as Solver};
use satcoder::*;
use satcoder::constraints::*;
use satcoder::symbolic::*;
//use std::fmt::Write;
use log::*;

use satcoder::constraints::*;
use satcoder::symbolic::*;
use satcoder::*;
use std::iter::{once, empty};
use std::hash::Hash;

//mod problem;
////mod construct;
//use problem::*;
pub type TeamId = i64;
pub type SlotId = i64;

pub fn lazy_break_var<L:Lit>(
    solver :&mut impl SatInstance<L>,
    break_vars :&mut HashMap<(SlotId, TeamId, bool), Bool<L>>,
    home_vars :&HashMap<(SlotId, TeamId), Bool<L>>,
    slot :SlotId,
    team :TeamId,
    is_home :bool) -> Bool<L> {

    if let Some(v) = break_vars.get(&(slot,team,is_home)) {
        assert!(slot != 0);
        return *v;
    }

    if slot == 0 {
        // There are no breaks in the first slot
        return false.into();
    }

    let v = SatInstance::new_var(solver);
    let home1 = home_vars[&(slot-1, team)];
    let home2 = home_vars[&(slot, team)];

    // NOTE we assume here that breaks are only limited, not enforced.
    // TODO confirm this assumption
    // Tried adding two-sided here to check performance, no difference so far.
    if is_home {
        SatInstance::add_clause(solver, vec![!home1, !home2, v]);
        SatInstance::add_clause(solver, vec![home1, !v]);
        SatInstance::add_clause(solver, vec![home2, !v]);
    } else {
        let away1 = !home1;
        let away2 = !home2;
        SatInstance::add_clause(solver, vec![!away1, !away2, v]);
        SatInstance::add_clause(solver, vec![away1, !v]);
        SatInstance::add_clause(solver, vec![away2, !v]);
    }

    break_vars.insert((slot, team, is_home), v);
    v
}

#[derive(Debug)]
pub struct CardinalityConstraint<L:Lit> {
    pub name :String,
    pub lits :Vec<Bool<L>>,
    pub min :Option<u32>,
    pub max :Option<u32>,
    pub cost :Option<u32>,
}


pub enum Soft<L: Lit> {
    Undef,
    Relaxable(usize, Bool<L>, Option<(usize, Relax<L>)>),
    Constructable(usize, Relax<L>),
}

impl<L:Lit> Default for Soft<L> {
    fn default() -> Self {
        Soft::Undef
    }
}

impl<L:Lit> Soft<L> {
    pub fn weight(&self) -> usize {
        match self {
            Soft::Relaxable(w,_,_) => *w,
            Soft::Constructable(w,_) => *w,
            _ => panic!(),
        }
    }
}

pub enum Relax<L:Lit> {
    Seq(Vec<Bool<L>>), // Just a list of lits where each lit in the list implies the next one in the list.

    NewCumDiff { 
        lits :Vec<(Bool<L>, Bool<L>)>,
        bound :usize,
    },

    NewUnary {
        lits :Vec<Bool<L>>,
        truncate: Option<usize>,
        min :Option<usize>,
        max :Option<usize>,
    },

    NewTotalizer {
        lits :Vec<Bool<L>>,
        bound: usize,
    },

    ExtendTotalizer(Totalizer<L>, u32), // A totalizer
    ExtendCumDiff { // A max diff constraint and the current bound
        diff: CumulativeDiff<L>,
        bound :usize,
    },

    Separation {
        t1 :TeamId,
        t2 :TeamId,
        min :usize,
    },

}

use structopt::*;
#[derive(StructOpt, Debug)]
struct Opt {
    #[structopt(required=true, name = "FILE", parse(from_os_str))]
    files :Vec<std::path::PathBuf>,

    #[structopt(short, long, parse(from_occurrences))]
    verbose: u8,

    #[structopt(short, long)]
    encode_only: bool,

    #[structopt(short, long)]
    to_cnf: bool,

    #[structopt(short, long)]
    feasibility_only: bool,

    #[structopt(short, long)]
    pattern_home_away: Option<std::path::PathBuf>,

    #[structopt(short, long)]
    br2_heuristic: bool,

    #[structopt(short, long)]
    xml_solutions: Option<std::path::PathBuf>,

    #[structopt(long)]
    feasibility_timeout: Option<f32>,

    #[structopt(long)]
    optimization_timeout: Option<f32>,

    #[structopt(long)]
    quiet: bool,

}

fn main() {

    let options = Opt::from_args();

    stderrlog::StdErrLog::new()
        .verbosity(options.verbose.into())
        .quiet(options.quiet)
        .module(module_path!())
        .module("dpllt")
        .show_module_names(true)
        .color(stderrlog::ColorChoice::Auto)
        .init().unwrap();


    let finalize_xml = options.xml_solutions.clone().map(|f| dispose::defer(move || {
        info!("Writing header/footer of xml solution set file");
        let contents = std::fs::read_to_string(&f).unwrap_or_else(|_| String::new());
        std::fs::write(&f, &format!("<MultipleSchedules>{}</MultipleSchedules>", contents)).unwrap();
        info!("Finished writing header/footer of xml solution set file");
    }));

    if let Some(f) = options.xml_solutions.as_ref() {
        // Clear the output file
        std::fs::write(f, "").unwrap();
    }


    info!("Arguments {:#?}", options);

    // Checking some encoding sizes
    //{
    //    let mut solver = satcoder::solvers::minisat::Solver::new();
    //    let n = 1540;
    //    let lits = (0..n).map(|_| SatInstance::new_var(&mut solver)).collect::<Vec<_>>();
    //    let sum = Unary::sum(&mut solver, lits.iter().map(|l| Unary::from_bool(*l) ).collect());
    //    println!("solver {:?}", solver);
    //}
    //{
    //    let mut solver = satcoder::solvers::minisat::Solver::new();
    //    let n = 1540;
    //    let lits = (0..n).map(|_| SatInstance::new_var(&mut solver)).collect::<Vec<_>>();
    //    let sum = Unary::sum_truncate(&mut solver, lits.iter().map(|l| Unary::from_bool(*l) ).collect(), 78);
    //    println!("solver {:?}", solver);
    //}

    //return;


    let instance_fn = &options.files[0];
    info!("Loading xml {:?}", instance_fn);
    let instance_xml = std::fs::read_to_string(instance_fn).unwrap();
    info!("Loaded {} chars", instance_xml.len());

    let doc = roxmltree::Document::parse(&instance_xml).unwrap();
    info!("Parsed document ");


    // Check the header
    //info!("{:?}", doc.root_element());
    assert!(doc.root_element().tag_name().name() == "Instance");
    let metadata = doc.root_element().children().find(|n| n.tag_name().name() == "MetaData").unwrap();
    info!("MetaData {}", &instance_xml[metadata.range()]);

    // Check that we have the main document elements
    let resources = doc.root_element().children().find(|n| n.tag_name().name() == "Resources").unwrap();
    let structure = doc.root_element().children().find(|n| n.tag_name().name() == "Structure").unwrap();
    let constraints = doc.root_element().children().find(|n| n.tag_name().name() == "Constraints").unwrap();
    let objective = doc.root_element().children().find(|n| n.tag_name().name() == "ObjectiveFunction").unwrap();


    // Representation:
    // Even number of teams.
    // Total number of time slots is equal to the total number of games per team,
    // so each team plays exactly one game per time slot.

    // Resources
    let leagues = resources.children().find(|n| n.tag_name().name() == "Leagues").unwrap();
    assert!(leagues.children().filter(|n| n.is_element()).count() == 1);
    let league = leagues.first_element_child().unwrap();

    let teams = resources.children().find(|n| n.tag_name().name() == "Teams").unwrap();
    let mut team_ids = Vec::new();
    for team in teams.children().filter(|n| n.is_element()) {
        //println!("Team {}", &instance_xml[team.range()]);
        assert!(team.attribute("league") == league.attribute("id"));
        team_ids.push(team.attribute("id").unwrap().parse::<i64>().unwrap());
    }

    info!("teams: {:?}", team_ids);

    let slots = resources.children().find(|n| n.tag_name().name() == "Slots").unwrap();
    let mut slot_ids = Vec::new();
    for slot in slots.children().filter(|n| n.is_element()) {
        slot_ids.push(slot.attribute("id").unwrap().parse::<i64>().unwrap());
    }

    info!("slots: {:?}", slot_ids);

    if team_ids.len() == 16 { assert!(slot_ids.len() == 30); }
    if team_ids.len() == 18 { assert!(slot_ids.len() == 34); }
    if team_ids.len() == 20 { assert!(slot_ids.len() == 38); }
    assert!( 2 * (team_ids.len() - 1) == slot_ids.len() );

    // ## REPRESENTATION
    //let mut solver = Solver::new(Default::default());
    let mut solver = Solver::new();
    let mut break_vars :HashMap<(SlotId, TeamId, bool), _> = HashMap::new();
    //let mut solver = satcoder::dimacsoutput::DimacsOutput::new();
    //solver.cadical.set_option("verbose",0).unwrap();




    // Format
    let format = structure.children().find(|n| n.tag_name().name() == "Format").unwrap();
    info!("format: {}", &instance_xml[format.range()]);

    // Must be 2RR format
    assert!(format.children().find(|n| n.tag_name().name() == "numberRoundRobin").unwrap().text() == Some("2"));

    // Can be phased
    let phased : bool = format.children().find(|n| n.tag_name().name() == "gameMode").unwrap().text().unwrap() == "P";
    info!("PHASED: {}", phased);

    // Must be compact
    let compact : bool = format.children().find(|n| n.tag_name().name() == "compactness").unwrap().text().unwrap() == "C";
    assert!(compact);

    let (matched_vars, home_vars) = encode_compact_2rr(&mut solver,
                                              &slot_ids ,&team_ids, phased);


    info!("Compact 2RR vars {} clauses {}", solver.cadical.num_variables(), solver.cadical.num_clauses());
    //// Enforce phased layout
    //if phased {
    //    assert_phased(&mut solver, &slot_ids, &team_ids, |s,t1,t2| matched_vars[&(s,(t1,t2))]);
    //}
    
    let mut soft :Vec<Soft<_>>= encode_constraints(&mut solver, &constraints, &matched_vars, &home_vars,&mut break_vars,
                                              &team_ids ,&slot_ids, options.br2_heuristic);



    info!("Problem has vars{} clauses{}", solver.cadical.num_variables(), solver.cadical.num_clauses());

    if options.to_cnf {
        let mut problem = satcoder::dimacsoutput::DimacsOutput::new();

        let (matched_vars, home_vars) = encode_compact_2rr(&mut problem, &slot_ids ,&team_ids, phased);
        info!("Compact 2RR vars {} clauses {}", solver.cadical.num_variables(), solver.cadical.num_clauses());
        let _soft = encode_constraints(&mut problem, &constraints, &matched_vars, &home_vars, &mut HashMap::new(), &team_ids ,&slot_ids, false);

        let mut cnf = String::new();
        problem.write(&mut cnf).unwrap();

        let filename = format!("{}.cnf", instance_fn.to_str().unwrap());
        std::fs::write(&filename, &cnf).expect("Unable to write file");
        info!("Wrote cnf file {}", filename);
    }

    if options.encode_only {
        return;
    }

    if let Some(path) = options.pattern_home_away {
        let pattern_str = std::fs::read_to_string(path).unwrap();
        let teams = pattern_str.lines().collect::<Vec<_>>();
        assert!(teams.len() == team_ids.len());
        assert!(teams.iter().all(|s| s.len() == slot_ids.len()));

        for (team_idx, slots) in teams.iter().enumerate() {
            for (slot_idx, home_char) in slots.chars().enumerate() {

                let home = match home_char {
                    '1' => true,
                    '0' => false,
                    _ => panic!(),
                };


                let var = home_vars[&(slot_idx as SlotId,  team_idx as TeamId)];
                let l = if home { var } else { !var };
                //println!("slot {} team {} forced to be {:?}", slot_idx, team_idx, l);
                SatInstance::add_clause(&mut solver, vec![l]);
            }
        }
        info!("Forced home-away pattern.");

    }

    info!("Problem has vars{} clauses{}", solver.cadical.num_variables(), solver.cadical.num_clauses());

    // simplify
    solver.cadical.set_limit("preprocessing", 10000).unwrap();
    solver.cadical.set_limit("conflicts", 2).unwrap();
    solver.cadical.solve();
    info!("Problem has vars{} clauses{}", solver.cadical.num_variables(), solver.cadical.num_clauses());

    //
    //
    // Check feasibility
    //
    //


    solver.cadical.set_callbacks(None);
    if let Some(to) = options.feasibility_timeout {
        println!("setting timeout {:?}", to);
        solver.cadical.set_callbacks(Some(satcoder::solvers::cadical::Timeout::new(to)));
    }

    let result = solver.solve_with_assumptions(std::iter::empty());


    match result {
        SatResultWithCore::Sat(ref model) => {
            assert!(verify_schedule( &slot_ids, &team_ids, phased, |s,t1,t2| model.value(&matched_vars[&(s,(t1,t2))])));
            let out = format_schedule(&slot_ids, &team_ids, |s,t1,t2| model.value(&matched_vars[&(s,(t1,t2))]));
            if !options.quiet {
                println!("{}", out);
            }

            let out = format_schedule_xml(instance_fn.to_str().unwrap(), &slot_ids, &team_ids, |s,t1,t2| model.value(&matched_vars[&(s,(t1,t2))])).unwrap();
            if !options.quiet {
                println!("{}", out);
            }

            if let Some(xml_out) = options.xml_solutions.clone() {
                eprintln!("Writing feasible solution to {:?}", xml_out);
                use std::fs::OpenOptions;
                use std::io::prelude::*;
                let mut file = OpenOptions::new().create(true).append(true).open(xml_out).unwrap(); 
                writeln!(file, "{}", out).unwrap();
            }

            info!("Feasible solution found.");
        },
        SatResultWithCore::Unsat(_) => { panic!("unsat"); }
    }
    drop(result);

    if options.br2_heuristic {
        // make all break vars
        for slot in slot_ids.iter().copied() {
            for team in team_ids.iter().copied() {
                for is_home in vec![true, false ] {
                    lazy_break_var(&mut solver, &mut break_vars, &home_vars, slot, team, is_home);
                }
            }
        }

        br2_heuristic(&mut solver, &constraints, &break_vars, &team_ids, &slot_ids);
        return;
    }

    if options.feasibility_only {
        info!("feasible solution found. exiting.");
        return;
    }

    //
    //
    // Then optimize
    //
    //
    //
    soft.sort_by_key(|s| -(s.weight() as isize));
    let weight_groups = soft.iter().group_by(|s| s.weight()).into_iter().map(|(key,g)| (key, g.collect::<Vec<_>>())).collect::<Vec<(usize, Vec<_>)>>();
    let mut current_lb = 0;
    let mut max_constraints = 
        vec![
            weight_groups.iter().nth(0).map(|(_,v)| v.len()).unwrap_or(soft.len()),
            soft.len() / 10
        ].into_iter().max().unwrap();
    let mut max_constraints = 10;
    let max_constraints_step = max_constraints;

    //assert!(soft.iter().all(|x| x.lit.is_err()));
    
    let mut remaining_optimization_time = options.optimization_timeout.clone();


    'optimize: loop {

        info!("Preparing soft constraint assumptions");

        soft.sort_by_key(|s| -(s.weight() as isize));
        let weight_groups = soft.iter().group_by(|s| s.weight()).into_iter().map(|(key,g)| (key, g.collect::<Vec<_>>())).collect::<Vec<(usize, Vec<_>)>>();
        info!("Weight groups: {:?}", weight_groups.iter().map(|(key,g)| (key,g.len())).collect::<Vec<_>>());
        let highest_weight = weight_groups.iter().map(|(key,_)| *key).nth(0).unwrap_or(1);
        drop(weight_groups);


        let mut n_assumptions = 0;
        // Pass over the soft list set and assure that we have representations for
        // the constraints that we want to apply as assumptions in this iteration.
        loop {
            if n_assumptions >= soft.len() { break; }
            if n_assumptions >= max_constraints { break; }

            let s = &mut soft[n_assumptions];
            //if s.weight <= highest_weight/2 { break; }

            // Introduce the representation of the soft constraint, if necessary.

            if let Soft::Relaxable(c,_,_) = &soft[n_assumptions] {
                assert!(*c > 0); n_assumptions += 1; 
            } else {
                let old = std::mem::take(&mut soft[n_assumptions]);
                match old {

                    Soft::Constructable(cost, Relax::Seq(mut xs)) => {
                        assert!(xs.len() > 0);
                        let x = xs.remove(0);
                        assert!(x.lit().is_some());
                        let relax = if xs.len() > 0 { Some((cost, Relax::Seq(xs))) } else { None };
                        soft[n_assumptions] = Soft::Relaxable(cost, x, relax);
                        n_assumptions += 1;
                    },

                    // TOTALIZER
                    Soft::Constructable(cost, Relax::NewTotalizer { lits, bound }) => {
                        let tot = Totalizer::count(&mut solver, lits.clone(), bound as u32);
                        if (bound as usize) < tot.rhs().len() {
                            assert!(tot.rhs()[bound].lit().is_some());

                            soft[n_assumptions] = Soft::Relaxable(cost, !tot.rhs()[bound as usize], Some((cost, Relax::ExtendTotalizer(tot, bound as u32+1))));
                            n_assumptions += 1;
                        } else {
                            debug!("lits {:?}", lits);
                            debug!("bound {}", bound);
                            panic!("created an unnecessary totalizer?!");
                        }

                    },
                    Soft::Constructable(cost, Relax::ExtendTotalizer(mut tot,bound)) => {
                        tot.increase_bound(&mut solver, bound as u32);
                        if (bound as usize) < tot.rhs().len() {
                            assert!(tot.rhs()[bound as usize].lit().is_some());
                            soft[n_assumptions] = Soft::Relaxable(cost, !tot.rhs()[bound as usize], Some((cost, Relax::ExtendTotalizer(tot, bound as u32+1))));
                            n_assumptions += 1;
                        } else {
                            soft.remove(n_assumptions);
                        }
                    },

                    // CUMDIFF
                    Soft::Constructable(cost, Relax::NewCumDiff { lits, bound }) => {
                        let diff = CumulativeDiff::new( &mut solver, lits, bound as u32);
                        assert!(diff.exceeds(bound as u32).lit().is_some());
                        soft[n_assumptions] = Soft::Relaxable(cost, !diff.exceeds(bound as u32), Some((cost, Relax::ExtendCumDiff { diff, bound: bound +1 })));
                        n_assumptions += 1;
                    }

                    Soft::Constructable(cost, Relax::ExtendCumDiff { mut diff, bound }) => {
                        diff.extend(&mut solver, bound as u32);
                        assert!(diff.exceeds(bound as u32).lit().is_some());
                        //s.lit = Ok((!diff.exceeds(bound as u32), Some(Relax::ExtendCumDiff { diff, bound: bound +1 })));
                        soft[n_assumptions] = Soft::Relaxable(cost, !diff.exceeds(bound as u32), Some((cost, Relax::ExtendCumDiff { diff, bound: bound +1 })));
                        n_assumptions += 1;
                    },

                    Soft::Constructable(penalty, Relax::Separation { t1, t2, min }) => {
                        let separation_lte = (1i64..(min as i64 +1)).map(|n| (n, SatInstance::new_var(&mut solver))).collect::<Vec<_>>();
                        // lt x => lt x+1
                        for ((_,a),(_,b)) in separation_lte.iter().copied().zip(separation_lte.iter().skip(1).copied()) {
                            SatInstance::add_clause(&mut solver, vec![!a, b]);
                        }

                        for s1 in slot_ids.iter().copied() {
                            for s2 in slot_ids.iter().copied() {

                                if s2 <= s1 { continue; }

                                let diff = s2 - s1;
                                if let Some((_,sep_var)) = separation_lte.iter().find(|(n,_)| *n == diff) {
                                    SatInstance::add_clause( &mut solver, vec![ !matched_vars[&(s1, (t1, t2))], !matched_vars[&(s2, (t2, t1))], *sep_var ]);
                                    SatInstance::add_clause( &mut solver, vec![ !matched_vars[&(s1, (t1, t2))], !matched_vars[&(s2, (t1, t2))], *sep_var ]);
                                    SatInstance::add_clause( &mut solver, vec![ !matched_vars[&(s1, (t2, t1))], !matched_vars[&(s2, (t1, t2))], *sep_var ]);
                                    SatInstance::add_clause( &mut solver, vec![ !matched_vars[&(s1, (t2, t1))], !matched_vars[&(s2, (t2, t1))], *sep_var ]);
                                }
                            }
                        }
                        debug!("SE1 t1={} t2={} min={}", t1,t2,min);

                        let mut sep = separation_lte.into_iter().rev().map(|(_n,lit)| !lit).collect::<Vec<_>>();
                        let worst = sep.remove(0);
                        soft[n_assumptions] = Soft::Relaxable(penalty as _, worst, Some((penalty as _, Relax::Seq(sep))));
                        n_assumptions += 1;
                    },

                    // UNARY

                    Soft::Constructable(cost, Relax::NewUnary { lits, truncate, min, max }) => {
                        let lits_unary = lits.iter().map(|l| Unary::from_bool(*l)).collect::<Vec<_>>();
                        let sum = if let Some(truncate) = truncate {
                            //panic!("Soft constraint unary should not be trunacted.");
                            Unary::sum_truncate(&mut solver, lits_unary, truncate)
                        } else {
                            Unary::sum(&mut solver, lits_unary)
                        };

                        debug!("MIN {:?}", min);
                        debug!("MAX {:?}", max);
                        let min_lits = min.map(|min| (1..=min).rev().map(|n| sum.gte_const(n as isize)).collect::<Vec<_>>());
                        let max_lits = max.map(|max| (max..=(lits.len() as usize)).map(|n| sum.lte_const(n as isize)).collect::<Vec<_>>());
                        debug!("MIN_lits {:?}", min_lits);
                        debug!("MAX_lits {:?}", max_lits);

                        soft.remove(n_assumptions);

                        if let Some(mut min_lits) = min_lits {
                            let min_first = min_lits.remove(0);
                            assert!(min_first.lit().is_some());

                            soft.insert(n_assumptions, Soft::Relaxable(
                                cost,
                                min_first, 
                                (min_lits.len() > 0).then(|| (cost, Relax::Seq(min_lits)))));
                            n_assumptions += 1;
                        }

                        if let Some(mut max_lits) = max_lits {
                            let max_first = max_lits.remove(0);
                            assert!(max_first.lit().is_some());

                            soft.insert(n_assumptions, Soft::Relaxable(
                                cost,
                                max_first, 
                                (max_lits.len() > 0).then(|| (cost, Relax::Seq(max_lits)))));
                            //soft.insert(n_assumptions, Soft {
                            //    weight,
                            //    lit: Ok((max_first, (max_lits.len() > 0).then(|| Relax::Seq(max_lits))))
                            //});
                            n_assumptions += 1;
                        }
                    },
                    _ => { panic!(); },
                };
            }
        }

        debug!("taking {} from soft#{}", n_assumptions, soft.len());

        let lit_map : HashMap<_,usize> = soft.iter().enumerate().take(n_assumptions)
            .map(|(idx,soft)| {
                let lit = if let Soft::Relaxable(_cost,lit,_) = soft { *lit } else { panic!() };
                (lit, idx)
            }).collect();
        //println!("lit map {:?}", lit_map);

        assert!(lit_map.iter().all(|(l,_i)| l.lit().is_some()));

        info!("Prepared {}/{} assumptions with weights from {} to {}", 
              lit_map.len(),
              soft.len(),
              lit_map.iter().map(|(_,idx)| soft[*idx].weight()).min().unwrap_or(0),
              lit_map.iter().map(|(_,idx)| soft[*idx].weight()).max().unwrap_or(0));


        info!("solver {:?}", solver);
        info!("match vars {}, home vars {}", matched_vars.len(), home_vars.len());
        info!("Solving with vars{} clauses{}", solver.cadical.num_variables(), solver.cadical.num_clauses());
        info!("LB: {}", current_lb);
        info!("Solving...");


        solver.cadical.set_callbacks(None);
        if let Some(to) = remaining_optimization_time.as_ref() {
            solver.cadical.set_callbacks(Some(satcoder::solvers::cadical::Timeout::new(*to)));
        }

        let start = Instant::now();
        let result = solver.solve_with_assumptions(lit_map.keys().copied());
        let duration = start.elapsed();


        if let Some(to) = remaining_optimization_time.as_mut() {
            *to -= duration.as_secs_f32();
        }

        match result {
            SatResultWithCore::Sat(model) => {

                info!("model");

                assert!(verify_schedule( &slot_ids, &team_ids, phased, |s,t1,t2| model.value(&matched_vars[&(s,(t1,t2))])));
                let out = format_schedule(&slot_ids, &team_ids, |s,t1,t2| model.value(&matched_vars[&(s,(t1,t2))]));
                if !options.quiet {
                    println!("{}", out);
                }

                let out = format_schedule_xml(instance_fn.to_str().unwrap(), &slot_ids, &team_ids, |s,t1,t2| model.value(&matched_vars[&(s,(t1,t2))])).unwrap();
                if !options.quiet {
                    println!("{}", out);
                }

                if let Some(xml_out) = options.xml_solutions.clone() {
                    eprintln!("Writing feasible solution to {:?}", xml_out);
                    use std::fs::OpenOptions;
                    use std::io::prelude::*;
                    let mut file = OpenOptions::new().create(true).append(true).open(xml_out).unwrap(); 
                    writeln!(file, "{}", out).unwrap();
                }

                if lit_map.len() < soft.len() {
                    let old_c = max_constraints;
                    max_constraints += max_constraints_step;
                    info!("Increasing number of soft constraints from {} to {}.", old_c, max_constraints);
                } else {
                    info!("All done, optimum found as cost {}!", current_lb);
                    break 'optimize;
                }
            },
            SatResultWithCore::Unsat(ref conflict) => {
                if conflict.len() == 0 {
                    info!("The problem is infeasible!");
                    println!("infeasible");
                    break 'optimize;
                }
                debug!("Conflict set:  {:?}", conflict);

                let conflict_cost = conflict.iter().map(|lit| {
                    if let Soft::Relaxable(cost,_,_) = &soft[lit_map[&Bool::Lit(*lit)]] {
                        *cost
                    } else { panic!(); }}).min().unwrap();
                info!("Conflict cost {}", conflict_cost);

                let mut remove_softs = Vec::new();
                for l in conflict.iter().copied().map(Bool::Lit) {
                    let idx = lit_map[&l];

                    if let Soft::Relaxable(cost, _lit, relax) = &mut soft[idx] {

                        assert!(*cost >= conflict_cost);
                        if *cost > conflict_cost {
                            *cost -= conflict_cost;
                        } else {
                            if let Some((new_cost, relax)) = relax.take() {
                                soft[idx] = Soft::Constructable(new_cost, relax);
                            } else {
                                remove_softs.push(idx);
                            }
                        }

                    } else {
                        panic!("conflict includes not-yet-constructed constraint");
                    }
                }

                remove_softs.sort_by_key(|x| -(*x as isize));
                for idx in remove_softs { soft.remove(idx); }

                let c = if conflict.len() > 1 {
                    let insert_idx :usize = soft.binary_search_by_key(&conflict_cost, |s|  s.weight())
                        .or_else::<usize,_>(|idx| Ok(idx)).unwrap();

                    soft.insert(insert_idx, Soft::Constructable(conflict_cost,
                        Relax::NewTotalizer {
                            lits: conflict.into_iter().copied().map(|l| Bool::Lit(!l)).collect(),
                            bound: 1
                        }));
                    None
                } else {
                    Some(conflict[0])
                };



                drop(result);
                if let Some(c) = c { 
                    SatInstance::add_clause(&mut solver, vec![!c]);
                }

                let old_lb = current_lb;
                current_lb += conflict_cost;
                info!("LB increased from {} to {}", old_lb, current_lb);
            },
        };

    }
}

pub fn br2_heuristic<L:Lit + std::fmt::Debug>(solver :&mut (impl SatInstance<L> + SatSolverWithCore<Lit=L>),
                                              constraints :&roxmltree::Node,
                                              break_vars :&HashMap<(SlotId, TeamId, bool), Bool<L>>,
                                              team_ids :&[TeamId],
                                              slot_ids :&[SlotId]) {

    let all_breaks = break_vars.iter().map(|(_k,v)| !*v).collect::<HashSet<_>>();
    let mut breaks = break_vars.iter().map(|(_k,v)| !*v).collect::<HashSet<_>>();
    let intp = global_br2(constraints, team_ids, slot_ids).unwrap();
    loop {
        println!("solving with {} nonbreaks, i.e. max {} breaks", breaks.len(), all_breaks.len() - breaks.len());
        match solver.solve_with_assumptions(breaks.iter().copied()) {
            SatResultWithCore::Sat(m) => {
                let mut broken = Vec::new();
                for l in all_breaks.iter().copied() {
                    if m.value(&!l) {
                        broken.push(l);
                    }
                }
                println!("{}/{} breaks", broken.len(), intp);
            }
            SatResultWithCore::Unsat(core) => {
                println!("Core length {}", core.len());
                for c in core.iter().copied() {
                    assert!(breaks.remove(&Bool::Lit(c)));
                }
            },
        }
    }


}

fn global_br2(constraints :&roxmltree::Node, team_ids :&[TeamId], slot_ids :&[SlotId]) -> Result<usize, ()> {
    let break_constraints = constraints.children().find(|n| n.tag_name().name() == "BreakConstraints");
    if let Some(break_constraints) = break_constraints {
        for c in break_constraints.children().filter(|n| n.is_element()) {

            let hard = match c.attribute("type") {
                Some("HARD") => true,
                Some("SOFT") => false,
                _ => panic!("unknown type"),
            };

            let penalty = c.attribute("penalty").map(|x| x.parse::<u32>().unwrap());
            let min = c.attribute("min").map(|m| m.parse::<i64>().unwrap());
            let max = c.attribute("max").map(|m| m.parse::<i64>().unwrap());

            // If a team plays a game with the same home-away status as its previous game, we say it has a
            // break. As an example, team 2 in Table 2 has a home break in time slot s3 and s4. Breaks usually
            // are undesired since they have an adverse impact on game attendance (see [2]) and they can be
            // perceived as unfair due to the home advantage (e.g., [6]). Break constraints therefore regulate
            // the frequency and timing of breaks in a competition.


            if c.tag_name().name() == "BR2" {
                    let teams = c.attribute("teams").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
                    let slots = c.attribute("slots").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
                    let mode1_is_regular = c.attribute("mode1") == Some("REGULAR");
                    let home_mode_is_ha = c.attribute("homeMode") == Some("HA");
                    assert!(mode1_is_regular || home_mode_is_ha);
                    let is_global_br2 = hard && teams.len() == team_ids.len() && slots.len() == slot_ids.len();
                    if !is_global_br2 { continue ; }
                    let intp = c.attribute("intp").map(|m| m.parse::<usize>().unwrap()).unwrap();
                    return Ok(intp);
            }
        }
    }
    Err(())
}

pub fn encode_constraints<L:Lit + std::fmt::Debug>(solver :&mut impl SatInstance<L>, 
                                 constraints :&roxmltree::Node,
                                 matched_vars :&HashMap<(SlotId, (TeamId, TeamId)), Bool<L>>,
                                 home_vars :&HashMap<(SlotId, TeamId), Bool<L>>,
                                 break_vars :&mut HashMap<(SlotId, TeamId, bool), Bool<L>>,
                                 team_ids :&Vec<TeamId>,
                                 slot_ids :&Vec<SlotId>,
                                 skip_br2 :bool,
        ) -> Vec<Soft<L>> {

    let mut card = Vec::new();
    let mut soft :Vec<Soft<_>>= Vec::new();

    // # Constraints
    // 9 constraint types follow, all can be either soft or hard?

    // ## Capactiy constraints (4 pcs.)

    // Constraints may be optional
    let capacity_constraints = constraints.children().find(|n| n.tag_name().name() == "CapacityConstraints");
    let game_constraints = constraints.children().find(|n| n.tag_name().name() == "GameConstraints");
    let break_constraints = constraints.children().find(|n| n.tag_name().name() == "BreakConstraints");
    let fairness_constraints = constraints.children().find(|n| n.tag_name().name() == "FairnessConstraints");
    let separation_constraints = constraints.children().find(|n| n.tag_name().name() == "SeparationConstraints");

    let mut all_ca4_normal = Vec::new();

    if let Some(capacity_constraints) = capacity_constraints {
        for c in capacity_constraints.children().filter(|n| n.is_element()) {

            let hard = match c.attribute("type") {
                Some("HARD") => true,
                Some("SOFT") => false,
                _ => panic!("unknown type"),
            };

            let penalty = c.attribute("penalty").unwrap().parse::<i64>().unwrap();

            match c.tag_name().name() {

                "CA1" => {

                    //println!("capacity {}", &instance_xml[c.range()]);
                    let home = match c.attribute("mode") {
                        Some("H") => true,
                        Some("A") => false,
                        _ => panic!(),
                    };

                    let teams = c.attribute("teams").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
                    let slots = c.attribute("slots").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
                    let max = c.attribute("max").unwrap().parse::<u32>().unwrap();
                    let min = c.attribute("min").map(|m| m.parse::<u32>().unwrap());
                    let penalty = c.attribute("penalty").map(|m| m.parse::<u32>().unwrap());

                    //println!("Teams {:?}", teams);
                    //println!("Slots {:?}", slots);
                    //println!("max {:?}", max);
                    //println!("min {:?}", min);
                    //println!("penalty {:?}", penalty);
                    //println!("");

                    // Constraint CA1 is of fundamental use in sports timetabling to model ‘place constraints’ that
                    // forbid a team to play a home game or away game in a given time slot. Constraint CA1 can
                    // also help to balance the home-away status of games over time and teams. For example, when
                    // the home team receives ticket revenues, teams often request to have a limit on the number of
                    // away games they play during the most lucrative time slots. Note that a CA1 constraint where the
                    // set teams contains more than one team can be split into several CA1 constraints where the set
                    // teams contains one team: in all ITC2021 instances, teams therefore contains only one team
                    // 
                    // Each team from teams plays at most max home games (mode = "H") or away games
                    // (mode = "A") during time slots in slots. Team 0 cannot play at home on time slot 0.
                    // Each team in teams triggers a deviation equal to the number of home games (mode = "H")
                    // or away games (mode = "A") in slots more than max

                    assert!(min == None || min == Some(0));


                    assert!(teams.len() == 1);
                    let team = teams[0];

                    let count_vars = slots.iter().copied().map(|slot| {
                        let home_var = home_vars[&(slot, team)];
                        if home { home_var } else { !home_var }
                    }).collect::<Vec<_>>();

                    let name = format!("CA1 teams={:?} home={:?} slots={:?} min={:?} max={:?} hard={:?}", teams, home, slots, min, max, hard);
                    card.push(CardinalityConstraint { name, lits: count_vars, min, max: Some(max), 
                        cost: (!hard).then(|| penalty.unwrap()) });
                },
                "CA2" => {
                    let home = match c.attribute("mode1") {
                        Some("H") => Some(true),
                        Some("A") => Some(false),
                        Some("HA") => None,
                        _ => panic!(),
                    };

                    assert!(c.attribute("mode2") == Some("GLOBAL"));
                    let teams1 = c.attribute("teams1").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
                    let teams2 = c.attribute("teams2").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
                    let slots = c.attribute("slots").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
                    let max = c.attribute("max").unwrap().parse::<u32>().unwrap();
                    let min = c.attribute("min").map(|m| m.parse::<u32>().unwrap());
                    let penalty = c.attribute("penalty").map(|m| m.parse::<u32>().unwrap());

                    //println!("CA2 {:?}", (teams1,teams2,slots,max,min,penalty));
                    //  Each team in teams1 plays at most max home games (mode1 = "H"), away games (mode1 =
                    //  "A"), or games (mode1 = "HA") against teams (mode2 = "GLOBAL"; the only mode we
                    //  consider) in teams2 during time slots in slots. Team 0 plays at most one game against
                    //  teams 1 and 2 during the first three time slots.
                    //  Each team in teams1 triggers a deviation equal to the number of home games (mode1 =
                    //  "H"), away games (mode1 = "A"), or games (mode1 = "HA") against teams in teams2
                    //  during time slots in slots more than max.
                    //  Constraint CA2 generalizes CA1 and can model ‘top team and bottom team constraints’ that 
                    //  prohibit bottom teams from playing all initial games against top teams. Note that a CA2 constraint
                    //  where the set teams contains more than one team can be split into several CA2 constraints where
                    //  the set teams contains one team: in all ITC2021 instances, teams therefore contains only one
                    //  team.

                    assert!(min == None || min == Some(0));

                    assert!(teams1.len() == 1);
                    let team = teams1[0];

                    let mut count_vars = Vec::new();
                    for slot in slots.iter().copied() {
                        for team2 in teams2.iter().copied() {
                            match home {
                                Some(true) => count_vars.push(matched_vars[&(slot, (team, team2))]),
                                Some(false) => count_vars.push(matched_vars[&(slot, (team2, team))]),
                                None => {
                                    count_vars.push(matched_vars[&(slot, (team, team2))]);
                                    count_vars.push(matched_vars[&(slot, (team2, team))]);
                                }
                            }
                        }
                    }

                    let name = format!("CA2 Over team {} slots {:?} teams2{:?}, home {:?} min={:?} max={:?}", team, slots, teams2, home, min, max);
                    card.push(CardinalityConstraint {
                        name,
                        lits: count_vars,
                        min,
                        max: Some(max),
                        cost: (!hard).then(|| penalty.unwrap()) });
                },
                "CA3" => {

                    let home = match c.attribute("mode1") {
                        Some("H") => Some(true),
                        Some("A") => Some(false),
                        Some("HA") => None,
                        _ => panic!(),
                    };
                    let teams1 = c.attribute("teams1").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
                    let teams2 = c.attribute("teams2").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
                    let max = c.attribute("max").unwrap().parse::<u32>().unwrap();
                    let intp = c.attribute("intp").unwrap().parse::<u32>().unwrap();
                    let min = c.attribute("min").map(|m| m.parse::<u32>().unwrap());
                    let penalty = c.attribute("penalty").map(|m| m.parse::<u32>().unwrap());

                    // DOn't support min
                    assert!(min == None || min == Some(0));
                    assert!(c.attribute("mode2") == Some("SLOTS"));

                    // Each team in teams1 plays at most max home games (mode1 = "H"), away games (mode1 =
                    // "A"), or games (mode1 = "HA") against teams in teams2 in each sequence of intp time
                    // slots (mode2 = "SLOTS"; the only mode we consider). Team 0 plays at most two consecutive games against teams 1, 2, and 3.
                    // Each team in teams1 triggers a deviation equal to the sum of the number of home games
                    // (mode1 = "H"), away games (mode1 = "A"), or games (mode1 = "HA") against teams in
                    // teams2 more than max for each sequence of intp time slots.
                    // In the ITC2021 competition, there are at most two CA3 hard constraints per problem instance
                    // which limit the maximal length of home stands (and/or away trips) by forbidding consecutive
                    // home breaks (and/or consecutive away breaks). Furthermore, there can be arbitrary many soft
                    // constraints that limit the total number of consecutive games against certain strength groups of
                    // teams

                    // Detect home stands limit
                    if teams1.len() == team_ids.len() && teams2.len() == team_ids.len() {

                        if home == None || intp != max+1 || !hard {
                            panic!("unexpected CA3 characteristics");
                        }

                        debug!("CA3 variant=standslimit");

                        for team in team_ids.iter().copied() {
                            for window_start in 0..=(slot_ids.len()-intp as usize) {
                                let slots = &slot_ids[window_start..(window_start+intp as usize)];
                                assert!(slots.len() == intp as usize);
                                SatInstance::add_clause(solver, slots.iter()
                                    .map(|s| 
                                         if home == Some(true) { 
                                            // At least one of the slots does not contain a home game
                                             !home_vars[&(*s, team)] 
                                         } else if home == Some(false) { 
                                            // At least one of the slots does not contain a away game
                                             home_vars[&(*s, team)] 
                                         } else { panic!() }));
                            }
                        }
                    } else {


                        // hope that t1 is not large
                        if teams1.len() > 8  {
                            warn!("perf: CA3 variant=normal has many teams in teams1!");
                        }

                        if teams2.len() == team_ids.len() {
                            panic!("CA3 normal complete teams2 case handling missing");
                        }

                        if hard{ println!("{:?}", c); panic!(); }

                        // One constraint for each t1
                        for t1 in teams1.iter().copied() {
                            // One constraint for each window
                            for window_start in 0..=(slot_ids.len() - intp as usize) {
                                let mut count_vars = Vec::new();
                                for slot in &slot_ids[window_start .. (window_start + intp as usize)] {
                                    for t2 in teams2.iter().copied() {
                                        match home {
                                            Some(true) => { count_vars.push(matched_vars[&(*slot, (t1,t2))]); },
                                            Some(false) => { count_vars.push(matched_vars[&(*slot, (t2,t1))]); },
                                            None => { 
                                                count_vars.push(matched_vars[&(*slot, (t1,t2))]); 
                                                count_vars.push(matched_vars[&(*slot, (t2,t1))]); 
                                            },
                                        };
                                    }
                                }

                                let name = format!("CA3 variant=normal");
                                card.push(CardinalityConstraint { name,
                                    lits: count_vars,
                                    min: None, // not supported
                                    max: Some(max),
                                    cost: (!hard).then(|| penalty.unwrap()),
                                });
                            }
                        }
                    }

                },
                "CA4" => {

                      // Teams in teams1 play at most max home games (mode1 = "H"), away games (mode1 =
                      // "A"), or games (mode1 = "HA") against teams in teams2 during time slots in slots
                      // (mode2 = "GLOBAL") or during each time slot in slots (mode2 = "EVERY"). Teams
                      // 0 and 1 together play at most three home games against teams 2 and 3 during the first two
                      // time slots.
                      // The set slots (mode2 = "GLOBAL") or each time slot in slots (mode2 = "EVERY") triggers a deviation equal to the number of games (i, j) (mode1 = "H"), (j, i) (mode1 = "A"), or
                      // (i, j) and (j, i) (mode1 = "HA") with i a team from teams1 and j a team from teams2 more
                      // than max.
                      // In contrast to CA2 and CA3 that define restrictions for each team in teams1, CA4 considers
                      // teams1 as a single entity. This constraint is typically used to limit the total number of games
                      // between top teams, or to limit the total number of home games per time slot when e.g. two teams
                      // share a stadium

                    let global = match c.attribute("mode2") {
                        Some("GLOBAL") => true,
                        Some("EVERY") => false,
                        _ => panic!(),
                    };

                    let home = match c.attribute("mode1") {
                        Some("H") => Some(true),
                        Some("A") => Some(false),
                        Some("HA") => None,
                        _ => panic!(),
                    };

                    //assert!(c.attribute("mode2") == Some("GLOBAL"));
                    let mut teams1 = c.attribute("teams1").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
                    teams1.sort();
                    let mut teams2 = c.attribute("teams2").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
                    teams2.sort();
                    let mut slots = c.attribute("slots").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
                    slots.sort();
                    let max = c.attribute("max").unwrap().parse::<u32>().unwrap();
                    let min = c.attribute("min").map(|m| m.parse::<u32>().unwrap());
                    let penalty = c.attribute("penalty").map(|m| m.parse::<u32>().unwrap());

                    debug!("CA4 slots {}/{} teams1 {}/{} teams2 {}/{}", slots.len(),slot_ids.len(),
                    teams1.len(), team_ids.len(), teams2.len(), team_ids.len());
                    all_ca4_normal.push(c);


                    if global {

                        let mut count_vars = HashSet::new();
                        if teams2.len() == team_ids.len() {
                            assert!(home != None); // Doesn't make sense 
                            for slot in slots.iter().copied() {
                                for team1 in teams1.iter().copied() {
                                    if let Some(true) = home {
                                        count_vars.insert(home_vars[&(slot, team1)]);
                                    } else if let Some(false) = home {
                                        count_vars.insert(!home_vars[&(slot, team1)]);
                                    }
                                }
                            }
                        }  else {
                            for slot in slots.iter().copied() {
                                for team1 in teams1.iter().copied() {
                                    for team2 in teams2.iter().copied() {
                                        if team1 == team2 { continue; }
                                        match home {
                                            Some(true) => { count_vars.insert(matched_vars[&(slot, (team1, team2))]); },
                                            Some(false) => { count_vars.insert(matched_vars[&(slot, (team2, team1))]); },
                                            None => {
                                                count_vars.insert(matched_vars[&(slot, (team1, team2))]);
                                                count_vars.insert(matched_vars[&(slot, (team2, team1))]);
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        let name = format!("CA4 Over mode2={:?} teams {:?} slots {:?} teams2{:?}, home {:?} min={:?} max={:?}", c.attribute("mode2"), teams1, slots, teams2, home, min, max);
                        card.push(CardinalityConstraint {
                            name,
                            lits: count_vars.into_iter().collect(),
                            min, 
                            max: Some(max),
                            cost: (!hard).then(|| penalty.unwrap()),
                        });
                    } else {
                        // One constraint for EVERY slot
                        for slot in slots.iter().copied() {
                            let mut count_vars = HashSet::new();
                            if teams2.len() == team_ids.len() {
                                assert!(home != None); // Doesn't make sense 
                                for team1 in teams1.iter().copied() {
                                    if let Some(true) = home {
                                        count_vars.insert(home_vars[&(slot, team1)]);
                                    } else {
                                        count_vars.insert(!home_vars[&(slot, team1)]);
                                    }
                                }
                            } else {
                                for team1 in teams1.iter().copied() {
                                    for team2 in teams2.iter().copied() {
                                        if team1 == team2 { continue; }
                                        match home {
                                            Some(true) => { count_vars.insert(matched_vars[&(slot, (team1, team2))]); },
                                            Some(false) => { count_vars.insert(matched_vars[&(slot, (team2, team1))]); },
                                            None => {
                                                count_vars.insert(matched_vars[&(slot, (team1, team2))]);
                                                count_vars.insert(matched_vars[&(slot, (team2, team1))]);
                                            }
                                        }
                                    }
                                }
                            }

                            let name = format!("CA4 Over mode2={:?} teams {:?} slots {:?} teams2{:?}, home {:?} min={:?} max={:?}", c.attribute("mode2"), teams1, slots, teams2, home, min, max);
                            card.push(CardinalityConstraint {
                                name,
                                lits: count_vars.into_iter().collect(),
                                min: min,
                                max: Some(max),
                                cost: (!hard).then(|| penalty.unwrap()),
                            });
                        }
                    }
                },
                _ => { panic!("Unknown capacity constraint element name") },
            }
        }
    }


    warn!("All CA4");
    all_ca4_normal.sort_by_key(|c| {
        let mut teams1 = c.attribute("teams1").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
        teams1.sort();
        teams1
    });
    for c in all_ca4_normal.iter() {
        //assert!(c.attribute("mode2") == Some("GLOBAL"));
        let mut teams1 = c.attribute("teams1").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
        teams1.sort();
        let mut teams2 = c.attribute("teams2").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
        teams2.sort();
        let mut slots = c.attribute("slots").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
        slots.sort();
        let max = c.attribute("max").unwrap().parse::<u32>().unwrap();
        let min = c.attribute("min").map(|m| m.parse::<u32>().unwrap());
        let penalty = c.attribute("penalty").map(|m| m.parse::<u32>().unwrap());

        debug!("CA4 slots {:?} teams1 {:?} teams2 {:?}", slots,
            teams1, 
            teams2, );
    }



    if let Some(game_constraints) = game_constraints {
        for c in game_constraints.children().filter(|n| n.is_element()) {
            assert!(c.tag_name().name() == "GA1");

            let hard = match c.attribute("type") {
                Some("HARD") => true,
                Some("SOFT") => false,
                _ => panic!("unknown type"),
            };

            let penalty = c.attribute("penalty").map(|x| x.parse::<u32>().unwrap());
            let min = c.attribute("min").map(|m| m.parse::<u32>().unwrap());
            let max = c.attribute("max").map(|m| m.parse::<u32>().unwrap());
            let slots = c.attribute("slots").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();

            let meetings = c.attribute("meetings").unwrap().split(";").filter_map(|pair|  {
                if pair == "" { return None; }
                let pair = pair.split(",").map(|i| i.parse::<i64>().unwrap()).collect::<Vec<_>>();
                assert!(pair.len() == 2);
                Some((pair[0], pair[1]))
            }).collect::<Vec<_>>();

            // At least min and at most max games from G = {(i1, j1), (i2, j2), . . . } take place during time
            // slots in slots. Game (0, 1) and (1, 2) cannot take place during time slot 3.
            // The set slots triggers a deviation equal to the number of games in meetings less than min
            // or more than max.
            // Constraint GA1 deals with fixed and forbidden game to time slot assignments. Examples include
            // the police that forbid to play high risk games during time slots in which other major events are
            // planned, and broadcasters that request at least one ‘top game’ or ‘classic game’ in each televised
            // time slot.

            //println!("GA1 {:?}", (penalty, hard, min, max, slots, meetings));


            let vs = &matched_vars;
            let count_vars = slots.iter()
                .flat_map(|s| meetings.iter().map(move |(t1,t2)| vs[&(*s, (*t1,*t2))])).collect::<Vec<_>>();

            let name = format!("GA1 meetings {:?} slots {:?} min {:?} max {:?}", meetings, slots, min, max);
            card.push(CardinalityConstraint {
                name,
                lits: count_vars,
                min,
                max,
                cost: (!hard).then(|| penalty.unwrap()),
            });
        }
    }

    if let Some(break_constraints) = break_constraints {
        for c in break_constraints.children().filter(|n| n.is_element()) {

            let hard = match c.attribute("type") {
                Some("HARD") => true,
                Some("SOFT") => false,
                _ => panic!("unknown type"),
            };

            let penalty = c.attribute("penalty").map(|x| x.parse::<u32>().unwrap());
            let min = c.attribute("min").map(|m| m.parse::<i64>().unwrap());
            let max = c.attribute("max").map(|m| m.parse::<i64>().unwrap());

            // If a team plays a game with the same home-away status as its previous game, we say it has a
            // break. As an example, team 2 in Table 2 has a home break in time slot s3 and s4. Breaks usually
            // are undesired since they have an adverse impact on game attendance (see [2]) and they can be
            // perceived as unfair due to the home advantage (e.g., [6]). Break constraints therefore regulate
            // the frequency and timing of breaks in a competition.


            match c.tag_name().name() {
                "BR1" => {

                    // Each team in teams has at most intp home breaks (homeMode = "H"), away breaks
                    // (homeMode = "A"), or breaks (homeMode = "HA") during time slots in slots. Team 0
                    // cannot have a break on time slot 1.
                    // Each team in teams triggers a deviation equal to the difference in the sum of home breaks,
                    // away breaks, or breaks during time slots in slots more than max.
                    // The BR1 constraint can forbid breaks at the beginning or end of the season, or can limit the total
                    // number of breaks per team. Note that a BR1 constraint where the set teams contains more than
                    // one team can be split into several BR1 constraints where the set teams contains one team: in all
                    // ITC2021 instances, teams therefore contains only one team.

                    let teams = c.attribute("teams").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
                    let slots = c.attribute("slots").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();

                    let intp = c.attribute("intp").map(|m| m.parse::<u32>().unwrap()).unwrap();

                    assert!(teams.len() == 1);
                    let team = teams[0];


                    // Intp works the same as Max here??
                    // Is MODE1 always LEQ?
                    // mode1 is wrongly called HomeMode in competition documentation?

                    let home = match c.attribute("mode2") {
                        Some("H") => Some(true),
                        Some("A") => Some(false),
                        Some("HA") => None,
                        _ => panic!(),
                    };

                    let mut count_vars = Vec::new();
                    for slot in slots.iter().copied() {
                        match home {
                            Some(is_home) => { count_vars.push(lazy_break_var(
                                        solver, break_vars, &home_vars, slot, team, is_home)); },
                            None => {
                                count_vars.push(lazy_break_var(
                                        solver, break_vars, &home_vars, slot, team, true));
                                count_vars.push(lazy_break_var(
                                        solver, break_vars, &home_vars, slot, team, false));
                            }
                        }
                    }

                    let name = format!("BR1 hard team {} slots {:?} home {:?} intp {:?}", team, slots, home, intp);
                    card.push(CardinalityConstraint {
                        name,
                        lits: count_vars,
                        min:None,
                        max: Some(intp),
                        cost: (!hard).then(|| penalty.unwrap()),
                    });
                },
                "BR2" => {
                    // The sum over all breaks (homeMode = "HA", the only mode we consider) in teams is no
                    // more than (mode2 = "LEQ", the only mode we consider) intp during time slots in slots.
                    // Team 0 and 1 together do not have more than two breaks during the first four time slots.
                    // The set teams triggers a deviation equal to the number of breaks in the set slots more than
                    // intp .
                    // Constraint BR2 can be used to limit the total number of breaks for a subset of teams. In real-life,
                    // this constraint is mostly used to limit the total number of breaks in the competition.

                    let mode1_is_regular = c.attribute("mode1") == Some("REGULAR");
                    let home_mode_is_ha = c.attribute("homeMode") == Some("HA");
                    assert!(mode1_is_regular || home_mode_is_ha);
                    //assert!(hard);


                    let teams = c.attribute("teams").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
                    let slots = c.attribute("slots").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
                    let intp = c.attribute("intp").map(|m| m.parse::<u32>().unwrap()).unwrap();

                    let is_global_br2 = hard && teams.len() == team_ids.len() && slots.len() == slot_ids.len();
                    if is_global_br2 && skip_br2 { warn!("skipping br2"); continue ; }

                    let mut count_vars = Vec::new();
                    for team in teams.iter().copied() {
                        for slot in slots.iter().copied() {
                            count_vars.push(lazy_break_var(
                                    solver, break_vars, &home_vars, slot, team, true));
                            count_vars.push(lazy_break_var(
                                    solver, break_vars, &home_vars, slot, team, false));
                        }
                    }

                    let name = format!("BR2 hard teams {:?} slots {:?} intp {:?}", teams, slots, intp);
                    card.push(CardinalityConstraint {
                        name,
                        lits: count_vars,
                        min: None,
                        max: Some(intp),
                        cost: (!hard).then(|| penalty.unwrap()),
                    });

                },
                _ => { panic!(); },
            }
        }
    }

    if let Some(fairness_constraints) = fairness_constraints {
        for c in fairness_constraints.children().filter(|n| n.is_element()) {

            assert!(c.tag_name().name() == "FA2");

            let hard = match c.attribute("type") {
                Some("HARD") => true,
                Some("SOFT") => false,
                _ => panic!("unknown type"),
            };

            let penalty = c.attribute("penalty").unwrap().parse::<i64>().unwrap();
            let min = c.attribute("min").map(|m| m.parse::<i64>().unwrap());
            let max = c.attribute("max").map(|m| m.parse::<i64>().unwrap());

            let teams = c.attribute("teams").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
            let slots = c.attribute("slots").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();
            let intp = c.attribute("intp").map(|m| m.parse::<u32>().unwrap()).unwrap();

            assert!(c.attribute("mode") == Some("H"));

            // Each pair of teams in teams has a difference in played home games (mode = "H", the only
            // mode we consider) that is not larger than intp after each time slot in slots. The difference
            // in home games played between the first three teams is not larger than 1 during the first four
            // time slots.
            // Each pair of teams in teams triggers a deviation equal to the largest difference in played
            // home games more than intp over all time slots in slots.
            // Constraints FA2 is typically used to enforce that a timetable is intp-ranking-balanced, meaning
            // that the difference in played home games between any two teams is smaller than intp at any
            // point in time

            // Each pair of teams (t1,t2):
            //  
            //   cost += max_s max(0, penalty * (|sum_{i=0..s} home(i,t1) - sum_{i=0..s} home(i,t2)| - intp))

            // NOTE first try with cumulative sum
            for team1 in teams.iter().copied() {
                for team2 in teams.iter().copied() {

                    // Unordered pairs of teams
                    if team2 <= team1 { continue; }

                    let vars=    slot_ids.iter().copied().map(|s| {

                            let t1_home = home_vars[&(s,team1)];
                            let t2_home = home_vars[&(s,team2)];
                            (t1_home, t2_home)
                    });


                    debug!("FA2 teams={:?} hard={:?} t1={:?} t2={:?}", teams, hard, team1, team2);
                    if hard {
                        let diff = CumulativeDiff::new( solver, vars, intp);
                        SatInstance::add_clause(solver, std::iter::once( !diff.exceeds(intp) ));
                    } else {
                        soft.push(Soft::Constructable(penalty as _, 
                                Relax::NewCumDiff {
                                lits: vars.collect(),
                                bound: intp as usize,
                            }));
                    }
                }
            }
        }
    }

    if let Some(separation_constraints) = separation_constraints {
        for c in separation_constraints.children().filter(|n| n.is_element()) {

            let hard = match c.attribute("type") {
                Some("HARD") => true,
                Some("SOFT") => false,
                _ => panic!("unknown type"),
            };

            let penalty = c.attribute("penalty").unwrap().parse::<i64>().unwrap();
            let min = c.attribute("min").map(|m| m.parse::<i32>().unwrap()).unwrap();
            let max = c.attribute("max").map(|m| m.parse::<i64>().unwrap());
            assert!(max == None);

            assert!(c.tag_name().name() == "SE1");

            let teams = c.attribute("teams").unwrap().split(";").map(|s| s.parse::<i64>().unwrap()).collect::<Vec<_>>();

            // Two games between the same pair of teams


            // Each pair of teams in teams has at least min time slots (mode1 = "SLOTS", the only mode
            // we consider) between two consecutive mutual games. There are at least 5 time slots between
            // the mutual games of team 0 and 1.
            // Each pair of teams in teams triggers a deviation equal to the sum of the number of time
            // slots less than min or more than max for all consecutive mutual games.
            // SE1 is typically used to express that two games with the same opponents are separated by at least
            // a given number of time slots. If a separation of at least one time slot is required, this constraint
            // is often called the ‘no-repeater’ constraint (see [1]).



            // Theory idea:
            // say min=10
            // create a variable for each pair of teams and a minimum separation, at first min=10.
            // Assume each of the pairs, theory propagates that whenever a team is assigned, the
            // next 10 slots do not contain the return match. Implicitly:
            //   for t1=a, t2=b, min=10: for all slots s: 
            //      match(s,t1,t2) => !match(s+1, t2,t1)
            //      match(s,t1,t2) => !match(s+2, t2,t1)
            //                    ...  match(s+..., t2, t1)
            // when relaxing, create another marker variable for t1=a,t2=b,min=9, and so on...


            // Windowed at-most-one


            for t1 in teams.iter().copied() {
                for t2 in teams.iter().copied() {

                    if t2 <= t1 { continue; }

                    soft.push(Soft::Constructable(penalty as _,
                            Relax::Separation { t1, t2, min: min as _ }));
                }
            }
        }
    }


    // Prepare all the cardinality constraints

    //let mut reduce = None;

    for mut card in card {
        //let vars_before = solver.cadical.num_variables();
        //let clauses_before = solver.cadical.num_clauses();

        if card.min == Some(0) { card.min = None; }
        if card.max.map(|x| x as usize >= card.lits.len()) == Some(true) { card.max = None; }

        debug!("CONSTRAINT: {}", &card.name);

        use satcoder::symbolic::*;

        // Heuristic for whether to do min and max together
        fn together(_lits :usize, min :Option<u32>, max :Option<u32>) -> bool {
            if let Some(min) = min {
                if let Some(max) = max {
                    return 3*(max-min) < min || (max <= min+2 && min <= 5)
                } 
            } 
            false
        }
        let is_together = together(card.lits.len(), card.min, card.max);

        if is_together && card.cost.is_none() {
            let min = card.min.unwrap();
            let max = card.max.unwrap();
            let sum = Unary::sum_truncate(solver, card.lits.iter().map(|l| Unary::from_bool(*l)).collect(), max as usize +1);
            // hard
            SatInstance::add_clause(solver, vec![sum.gte_const(min as isize)]);
            SatInstance::add_clause(solver, vec![sum.lte_const(max as isize)]);

            debug!(" - Hard min/max sorting network");
        } else if is_together && card.cost.is_some() && card.max.is_some() && 2*card.max.unwrap() > card.lits.len() as u32 {
            //let min = card.min.unwrap();
            //let max = card.max.unwrap();
            //let sum = Unary::sum(&mut solver, card.lits.iter().map(|l| Unary::from_bool(*l)).collect());

            //let mut min_lits = (1..=min).rev().map(|n| sum.gte_const(n as isize)).collect::<Vec<_>>();
            //let mut max_lits = (max..=(card.lits.len() as u32)).rev().map(|n| sum.lte_const(n as isize)).collect::<Vec<_>>();
            //warn!(" -- min_lits {:?}",min_lits);
            //warn!(" -- max_lits {:?}",max_lits);

            //let min_first = min_lits.remove(0);
            //let max_first = max_lits.remove(0);

            //relax.insert(min_first, Relax::Seq(min_lits));
            //relax.insert(max_first, Relax::Seq(max_lits));

            assert!(card.min.is_some());
            assert!(card.max.is_some());
            let n = card.lits.len();
            warn!("full unary sum over {:?} min={:?} max={:?}", n, card.min, card.max);
            let cost = card.cost.unwrap() as usize;
            soft.push(Soft::Constructable(cost, 
                    Relax::NewUnary {
                    truncate: None, 
                    lits: card.lits,
                    min :card.min.map(|m| m as usize).filter(|m| *m > 0),
                    max :card.max.map(|m| m as usize).filter(|m| *m < n),
                }));

            debug!(" - Soft min/max sorting network");
        } else {

            // Do each min/max separately
            let min = card.min.unwrap_or(0u32);
            let max = card.max.unwrap_or(card.lits.len() as u32);
            if !(min>0) && !((max as usize) < card.lits.len()) {
                warn!(" - No min or max! Constraint has no effect.");
            }

            if min > 0 && (max as usize) < card.lits.len() {
                warn!(" - Split min/max!");
            }

            if min > 0 {

                // Can we flip it?
                if 2*(min as usize) > card.lits.len() {
                    // Encode max card of the inverse lits
                    debug!("Soft totalizer on inverse minimum");
                    let inv_min = card.lits.len() as u32 - min;
                    if let Some(cost) = card.cost {
                        soft.push(Soft::Constructable(cost as usize, Relax::NewTotalizer {
                                lits: card.lits.iter().map(|l| !*l).collect(),
                                bound: inv_min as usize,
                            }));
                    } else {
                        let tot = Totalizer::count(solver, card.lits.iter().map(|l| !*l), inv_min);
                        debug!(" - Hard totalizer on inverse minimum");
                        SatInstance::add_clause(solver, vec![!tot.rhs()[inv_min as usize]]);
                    }
                } else {
                    // Need to do sorting circuit encoding

                    if let Some(cost) = card.cost {
                        debug!("Soft sorting network on min={:?} lits={:?}", min, card.lits);
                        soft.push(Soft::Constructable(cost as usize,
                            Relax::NewUnary {
                                truncate: Some(min as usize),
                                lits: card.lits.clone(),
                                min: Some(min as _),
                                max: None,
                            }));
                    } else {
                        let sum = Unary::sum_truncate(solver, card.lits.iter().map(|l| Unary::from_bool(*l)).collect(), min as usize);
                        SatInstance::add_clause(solver, vec![sum.gte_const(min as isize)]);
                        debug!(" - Hard sorting network on min");
                    }
                }

            }

            if (max as usize) < card.lits.len() {

                //// TODO Should we flip it?
                //if 3*(card.lits.len() - max) > card.lits.len() {
                //} else {
                //}

                if let Some(cost) = card.cost {
                    soft.push(Soft::Constructable(cost as usize,
                        Relax::NewTotalizer { lits: card.lits, bound :max as usize}));
                    debug!("Soft totalizer on max");
                } else {
                    if max == 0 {
                        for l in card.lits {
                            SatInstance::add_clause(solver, vec![!l]);
                        }
                    } else if max == 1 {
                        warn!(" - max=1 special case ATM over {} lits", card.lits.len());
                        solver.assert_at_most_one(card.lits);
                    //} else if max == 2 {
                    //    warn!(" - max=2 special case ATM2 over {} lits", card.lits.len());
                    //    solver.assert_at_most_two(card.lits);
                    } else if max > 10 && max as usize == card.lits.len()-1 {
                        panic!("opportunity here");
                    } else {
                        assert!(card.cost.is_none());
                        let tot = Totalizer::count(solver, card.lits, max);
                        SatInstance::add_clause(solver, vec![!tot.rhs()[max as usize]]);
                        debug!(" - Hard totalizer on max");
                    }
                }
            } 
        }

        //debug!(" - added {} vars {} clausees", solver.cadical.num_variables() - vars_before,
        //solver.cadical.num_clauses() - clauses_before);

    }

    soft
}



pub fn assert_phased<L: Lit>(
    solver: &mut impl SatInstance<L>,
    slot_ids: &[SlotId],
    team_ids: &[TeamId],
    match_vars: impl Fn(SlotId, TeamId, TeamId) -> Bool<L>)  {
    
    panic!("unused");

    // For every pair, at most one meeting in the first half slots
    for t1_idx in 0..(team_ids.len()) {
        for t2_idx in 0..(team_ids.len()) {

            if t2_idx <= t1_idx { continue; }


            for start in vec![0,slot_ids.len()/2] {
                let mut half_meetings = Vec::new();
                for slot_idx in start..(start+slot_ids.len()/2) {

                    let (s,t1,t2) = (slot_ids[slot_idx], team_ids[t1_idx], team_ids[t2_idx]);

                    half_meetings.push(match_vars(s, t1, t2));
                    half_meetings.push(match_vars(s, t2, t1));
                }

                // Using the totalizer is 50% slower on ITC2021_Early1. 
                // Using both together is 200% slower on ITC2021_early1.
                // The base AMO copns

                //let totalizer = Totalizer::count(solver, half_meetings.iter().copied(), 1);
                //SatInstance::add_clause(solver, vec![!totalizer.rhs()[1]]);

                solver.assert_at_most_one(half_meetings);
            }
        }
    }

    // need more variables for this?
    //
    // Let's try:
    //   in_first_half(team1,team2)
    //

    use std::iter::once;
    let mut first_half :HashMap<(TeamId,TeamId),_>= HashMap::new();
    for t1 in team_ids.iter().copied() {
        for t2 in team_ids.iter().copied() {
            if t1 == t2 { continue; }

            first_half.insert((t1,t2), SatInstance::new_var(solver));

            // first half
            let use_first_half = (&slot_ids[0..slot_ids.len()/2]).iter().map(|s| match_vars(*s, t1, t2));
            SatInstance::add_clause(solver, use_first_half.chain(once(!first_half[&(t1,t2)])));

            for slot in (&slot_ids[0..slot_ids.len()/2]).iter().copied() {
                SatInstance::add_clause(solver, vec![ !match_vars(slot, t1, t2), first_half[&(t1,t2)] ]);
            }

            // second half
            let use_second = (&slot_ids[slot_ids.len()/2..slot_ids.len()]).iter().map(|s| match_vars(*s, t1, t2));
            SatInstance::add_clause(solver, use_second.chain(once(first_half[&(t1,t2)])));

            for slot in (&slot_ids[slot_ids.len()/2 .. ]).iter().copied() {
                SatInstance::add_clause(solver, vec![ !match_vars(slot, t1, t2), !first_half[&(t1,t2)] ]);
            }
        }
    }

    for t1 in team_ids.iter().copied() {
        for t2 in team_ids.iter().copied() {
            if t2 <= t1 { continue; }
            SatInstance::add_clause(solver, vec![first_half[&(t1,t2)], first_half[&(t2,t1)]]);
            SatInstance::add_clause(solver, vec![!first_half[&(t1,t2)], !first_half[&(t2,t1)]]);
        }
    }



}

pub fn encode_compact_2rr<L: Lit, SlotId: Copy + Hash + Eq, TeamId: Copy + Hash + Eq + PartialOrd>(
    solver: &mut impl SatInstance<L>,
    slot_ids: &[SlotId],
    team_ids: &[TeamId],
    phased :bool,
) -> 
(HashMap<(SlotId, (TeamId, TeamId)), Bool<L>>,
 HashMap<(SlotId, TeamId), Bool<L>>)
 {

     // Example: 6 teams, 10 slots
     //
     // 0-1 1-3 
     // 2-3 3-0
     // 4-5 5-4
     //
     // Each match (ordered pair of teams) happens exactly once.
     // Each team plays exactly one match per slot.
     // Each return match happens in the other half of slots (0..s/2 and s/2..s).
     // 

    let mut matched_vars: HashMap<(SlotId, (TeamId, TeamId)), _> = HashMap::new();
    let mut home_vars :HashMap<(SlotId, TeamId), _> = HashMap::new();

    for slot in slot_ids.iter().copied() {
        for team1 in team_ids.iter().copied() {
            for team2 in team_ids.iter().copied() {
                if team1 == team2 {
                    continue;
                }

                matched_vars.insert((slot, (team1, team2)), SatInstance::new_var(solver));
            }
        }

        // COMPACT schedule constraint:
        // The team has to play exactly one match in each slot
        for team1 in team_ids.iter().copied() {
            let mut team_match_alternatives = Vec::new();
            for team2 in team_ids.iter().copied() {
                if team1 == team2 {
                    continue;
                }
                // Either home or away
                team_match_alternatives.push(matched_vars[&(slot, (team1, team2))]);
                team_match_alternatives.push(matched_vars[&(slot, (team2, team1))]);
            }

            solver.assert_exactly_one(team_match_alternatives);
            //solver.assert_at_most_one(team_match_alternatives);
        }

        // HOME VARS derived from matched_vars
        for team in team_ids.iter().copied() {
            home_vars.insert((slot, team), SatInstance::new_var(solver));

            //// home and away implications
            let home_lits = team_ids.iter().filter(|t2| **t2 != team).map(|t2| matched_vars[&(slot, (team, *t2))]);
            SatInstance::add_clause(solver, home_lits.chain(std::iter::once(!home_vars[&(slot, team)])));
            let away_lits = team_ids.iter().filter(|t2| **t2 != team).map(|t2| !matched_vars[&(slot, (team, *t2))]);
            SatInstance::add_clause(solver, away_lits.chain(std::iter::once(home_vars[&(slot, team)])));

        }
        for team1 in team_ids.iter().copied() {
            for team2 in team_ids.iter().copied() {
                if team1 == team2 { continue; }
                let matched = matched_vars[&(slot, (team1, team2))];
                SatInstance::add_clause(solver, vec![!matched, home_vars[&(slot, team1)]]);
                SatInstance::add_clause(solver, vec![!matched, !home_vars[&(slot, team2)]]);
            }
        }
    }

    // 2RR constraint:
    // Each match combination must happen in exactly one slot
    for team1 in team_ids.iter().copied() {
        for team2 in team_ids.iter().copied() {
            if team2 <= team1 {
                continue;
            }

            if !phased {

                let matches1 = slot_ids.iter().copied().map(|s| matched_vars[&(s, (team1, team2))]);
                let matches2 = slot_ids.iter().copied().map(|s| matched_vars[&(s, (team2, team1))]);
                solver.assert_exactly_one(matches1);
                solver.assert_exactly_one(matches2);

            } else {

                let first_half = SatInstance::new_var(solver);

                let matches1a = (&slot_ids[0..slot_ids.len()/2]).iter().copied().map(|s| matched_vars[&(s, (team1, team2))]);
                let matches1b = (&slot_ids[slot_ids.len()/2..]) .iter().copied().map(|s| matched_vars[&(s, (team1, team2))]);
                let matches2a = (&slot_ids[0..slot_ids.len()/2]).iter().copied().map(|s| matched_vars[&(s, (team2, team1))]);
                let matches2b = (&slot_ids[slot_ids.len()/2..]) .iter().copied().map(|s| matched_vars[&(s, (team2, team1))]);

                // If we have first half, then matches1a and matches2b
                solver.assert_exactly_one(once(!first_half).chain(matches1a));
                solver.assert_exactly_one(once(!first_half).chain(matches2b));
                // If we have seconds half, then matches2a and matches1b
                solver.assert_exactly_one(once( first_half).chain(matches1b));
                solver.assert_exactly_one(once( first_half).chain(matches2a));
            }
        }
    }

    (matched_vars, home_vars)
}

pub fn verify_schedule<SlotId: std::fmt::Display + Copy + Eq, TeamId: std::fmt::Display + Eq + Copy + Eq>(
    slot_ids: &[SlotId],
    team_ids: &[TeamId],
    phased: bool,
    is_matched: impl Fn(SlotId, TeamId, TeamId) -> bool) -> bool {

    // compact, in every slot, teams are matched
    for slot in slot_ids.iter().copied() {
        for t1 in team_ids.iter().copied() {
            // the team participates in exactly one game
            let team_games = team_ids.iter().copied().filter(|t2|  {
                // Ordered pairs
                if t1 == *t2 { return false; }
                return is_matched(slot, t1, *t2) || is_matched(slot, *t2, t1);
            }).count();

            if team_games != 1 { 
                println!("in slot s{}, t{} plays {} games", slot, t1, team_games);
                return false; 
            }
        }
    }

    // 2rr, every match happens in a slot (first component is home team, so 2rr requires both
    // permutations)
    for t1 in team_ids.iter().copied() {
        for t2 in team_ids.iter().copied() {
            // Ordered pairs
            if t1 == t2 { continue; }
            let match_slots = slot_ids.iter().copied().filter(|s| is_matched(*s, t1, t2));
            if match_slots.count() != 1 { return false; }
        }
    }

    // Phased
    if phased {
        for t1_idx in 0..(team_ids.len()) {
            // Unordered pairs
            for t2_idx in (t1_idx+1)..(team_ids.len()) {

                let t1 = team_ids[t1_idx];
                let t2 = team_ids[t2_idx];

                // Find the home slot and away slot for these teams.
                let home_slot = slot_ids.iter().copied().filter(|s| is_matched(*s, t1, t2)).collect::<Vec<_>>();
                let away_slot = slot_ids.iter().copied().filter(|s| is_matched(*s, t2, t1)).collect::<Vec<_>>();

                if home_slot.len() != 1 || away_slot.len() != 1 { return false; }

                let home_first_half = slot_ids.iter().position(|i| *i == home_slot[0]).unwrap() < slot_ids.len() / 2;
                let away_first_half = slot_ids.iter().position(|i| *i == away_slot[0]).unwrap() < slot_ids.len() / 2;

                // home and away matches happen in opposite slot halfs
                if home_first_half == away_first_half {
                    return false;
                }
            }
        }
    }


    return true;
}

pub fn format_schedule_xml<SlotId: std::fmt::Display + Copy, TeamId: std::fmt::Display + Eq + Copy>(
    filename :&str,
    slot_ids: &[SlotId],
    team_ids: &[TeamId],
    is_matched: impl Fn(SlotId, TeamId, TeamId) -> bool,
) -> Result<String, std::fmt::Error> {
    use std::fmt::Write;
    let mut out = String::new();

    let infeasibility = 0;
    let objective = 99999999;

    let my_name = "bjornarl";
    let instance_name = std::path::Path::new(filename).file_name().unwrap().to_str().unwrap();
    let solution_name = 
        format!("{}_{}_{}_{}_{}.xml",
                std::path::Path::new(filename).file_stem().unwrap().to_str().unwrap(),
                my_name,
                infeasibility,
                objective,
                "today");


    writeln!(&mut out, "<Solution>")?;
    writeln!(&mut out, "  <MetaData>")?;
    writeln!(&mut out, "    <InstanceName>{}</InstanceName>", instance_name)?;
    writeln!(&mut out, "    <SolutionName>{}</SolutionName>", solution_name)?;
    writeln!(&mut out, "    <ObjectiveValue infeasibility=\"{}\" objective=\"{}\" />", infeasibility, objective)?;
    writeln!(&mut out, "  </MetaData>")?;
    writeln!(&mut out, "  <Games>")?;

    for slot in slot_ids.iter() {
        for team1 in team_ids.iter() {
            for team2 in team_ids.iter() {
                if *team2 == *team1 {
                    continue;
                }

                if is_matched(*slot, *team1, *team2) {
                    writeln!(&mut out, "    <ScheduledMatch home=\"{}\" away=\"{}\" slot=\"{}\" />", *team1, *team2, *slot)?;
                }
            }
        }
    }

    writeln!(&mut out, "  </Games>")?;
    writeln!(&mut out, "</Solution>")?;

    Ok(out)
}

pub fn format_schedule<SlotId: std::fmt::Display + Copy, TeamId: std::fmt::Display + Eq + Copy>(
    slot_ids: &[SlotId],
    team_ids: &[TeamId],
    is_matched: impl Fn(SlotId, TeamId, TeamId) -> bool,
) -> String {
    use std::fmt::Write;
    let mut out = String::new();
    let mut columns = Vec::new();
    for slot in slot_ids.iter() {
        write!(&mut out, " {:^5} ", format!("s{}", slot)).unwrap();

        columns.push(Vec::new());
        for team1 in team_ids.iter() {
            for team2 in team_ids.iter() {
                if *team2 == *team1 {
                    continue;
                }

                if is_matched(*slot, *team1, *team2) {
                    columns.last_mut().unwrap().push((*team1, *team2));
                }
            }
        }
    }
    writeln!(&mut out, "").unwrap();
    assert!(columns.iter().all(|n| n.len() == columns[0].len()));
    for idx in 0..columns[0].len() {
        for c in columns.iter() {
            write!(&mut out, " {:>2},{:<2} ", c[idx].0, c[idx].1).unwrap();
        }
        writeln!(&mut out, "").unwrap();
    }

    out
}
