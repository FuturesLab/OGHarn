#!/usr/bin/env python

import engine
import harness_builder
import process_mx
import os, sys
import time
import signal
import yaml
from copy import deepcopy
import shutil
import argparse
import pathlib
import subprocess
import random

def dump_potential_args(functions):
    arg_dump = open(f"{output_dir}/debug-info/log_call_site_params.txt", "w")
    for func in functions.getAllFunctions():
        strbuild = f"{func.name} Potential Arguments: ["
        for arg_set in func.potential_arguments:
            strbuild += "["
            for arg in arg_set:
                if isinstance(arg, engine.literal_arg):
                    strbuild += arg.value + ", "
                elif isinstance(arg, engine.define_new_val_arg):
                    strbuild += arg.value + " VAR DECL(" + arg.definition + "), "
                elif isinstance(arg, engine.function_pointer_arg):
                    strbuild += arg.value + " FUNC PTR(" + arg.definition + "), "
            strbuild += "], "
        arg_dump.write(strbuild[:-2]+"]\n")
    arg_dump.close()

# Dumps all dependencies between functions for debugging purposes
def dump_dependencies(api_funcs):
    dependency_dump = open(f"{output_dir}/debug-info/log_potential_dependencies.txt", "w")
    for api_func in api_funcs.getAllFunctions():
        dependency_dump.write(f"Function: {api_func.name}\n")
        for dep in api_func.dependencies:
            dependency_dump.write(f"{dep}\n")
        dependency_dump.write("\n")
    dependency_dump.close()

# Dumps all relevant data in terms of function definitions, aliases, etc.
def dump_definitions(functions, macros, enums, function_pointers, aliases, compatible):
    function_dump = open(f"{output_dir}/debug-info/log_multiplier.txt", "w")

    function_dump.write("\nAuxiliary Functions:\n")
    for api_func in functions.auxiliaryFunctions:
        api_func = functions.auxiliaryFunctions[api_func]
        function_dump.write(f"{api_func.mult_ret.base_type + ('*' * api_func.mult_ret.pointers) } {api_func.name}\
({[arg.base_type + ('*' * arg.pointers) for arg in api_func.mult_args]})\
Status Check(operator: {api_func.ret_status_check[0]}, value: {api_func.ret_status_check[1]})\n")

    function_dump.write("\nSetup Functions:\n")
    for api_func in functions.setupFunctions:
        api_func = functions.setupFunctions[api_func]
        function_dump.write(f"{api_func.mult_ret.base_type + ('*' * api_func.mult_ret.pointers) } {api_func.name}\
({[arg.base_type + ('*' * arg.pointers) for arg in api_func.mult_args]})\
Status Check(operator: {api_func.ret_status_check[0]}, value: {api_func.ret_status_check[1]})\n")

    function_dump.write("\nProcessing Functions:\n")
    for api_func in functions.processingFunctions:
        api_func = functions.processingFunctions[api_func]
        function_dump.write(f"{api_func.mult_ret.base_type + ('*' * api_func.mult_ret.pointers) } {api_func.name}\
({[arg.base_type + ('*' * arg.pointers) for arg in api_func.mult_args]})\
Status Check(operator: {api_func.ret_status_check[0]}, value: {api_func.ret_status_check[1]})\n")

    function_dump.write("\nMacros:\n")
    for macro in macros:
        function_dump.write(f"{macro}\n")

    function_dump.write("\nEnums:\n")
    for enum in enums:
        function_dump.write(f"enum: {enum}\n")
        for val in enums[enum]:
            function_dump.write(f"\t{val}\n")

    function_dump.write("\nFunction Pointers:\n")
    for fp in function_pointers:
        func_def = function_pointers[fp]
        func_res = engine.multiplier_type()
        func_res = compatible.init_mult_type(func_def.call_result_type, func_res)
        func_params = []
        for param in func_def.parameter_types:
            mult_type = engine.multiplier_type()
            mult_type = compatible.init_mult_type(param, mult_type)
            func_params.append(mult_type)

        function_dump.write(
            f"{func_res.base_type + ('*' * func_res.pointers)} {fp}({[arg.base_type + ('*' * arg.pointers) for arg in func_params]})\n")

    function_dump.write("\nTypedef Aliases:\n")
    for alias_name in aliases:
        function_dump.write(f"alias: {alias_name}\n")
        for alias in aliases[alias_name]:
            if isinstance(alias, str):
                function_dump.write(f"\t{alias}\n")
            else:
                arg = engine.multiplier_type()
                arg = compatible.init_mult_type(alias, arg)
                function_dump.write(f"\t{arg.base_type + ('*' * arg.pointers)}\n")


def handle_interrupt(sig, frame):
    print("\nCtrl+C pressed! Terminating the process. Please be patient as the minimized harness corpus is generated.")
    # sleeping for a sec to let any other subprocesses finish
    time.sleep(2)
    try:
        exit_routine()
    # if an exit occurs before the compiler is defined, an exception occurs, we catch that
    except Exception as e:
        print(f"An exception occurred: {e}")
    os._exit(0)


def exit_routine():
    compiler.globalBitmap = set() # resetting bitmap for edge optimization
    if not args.target_func:
        if len(compiler.successfulSequences):
            final_sequences = compiler.successfulSequences + compiler.currIterSuccesses + compiler.routineSequences
        else:
            final_sequences = compiler.routineSequences + compiler.currIterSuccesses
    else:
        final_sequences = compiler.targetSequences + compiler.currIterSuccesses

    bestSequences = getBestHarnesses(compiler, final_sequences, float("inf"), final_corp=True)

    if not os.path.exists(f"{output_dir}/final-harnesses/"):
        os.mkdir(f"{output_dir}/final-harnesses/")
    if not os.path.exists(f"{output_dir}/final-harnesses/bin"):
        os.mkdir(f"{output_dir}/final-harnesses/bin")
    if not os.path.exists(f"{output_dir}/final-harnesses/src"):
        os.mkdir(f"{output_dir}/final-harnesses/src")
    harnessCount = 0
    for harness in bestSequences:
        harnessCount += 1
        currFile = open(f"{output_dir}/final-harnesses/src/harness{harnessCount}:{harness.effectiveness}-new-tuples.c", "w")
        harnessFile = open(f"{output_dir}/gen/harness.c", "w")
        currFile.write(harness.cCode)
        harnessFile.write(harness.cCode)
        currFile.close()
        harnessFile.close()
        #storing binaries
        proc = subprocess.run(f"cd {input_dir} && OUT={output_dir}/gen make harness", stderr=subprocess.PIPE, stdout=subprocess.PIPE,
                              text=True, shell=True)
        subprocess.run(f"mv {output_dir}/gen/harness.out {output_dir}/final-harnesses/bin/harness{harnessCount}.out", text=True, shell=True)
        compiler.globalBitmap = compiler.globalBitmap.union(harness.bitmap)
    fstr = f"Total coverage captured between {harnessCount} files in {output_dir}/final-harnesses: {len(compiler.globalBitmap)}\n"
    os.write(sys.stdout.fileno(), b"DONE!\n")
    os.write(sys.stdout.fileno(), bytes(fstr, 'utf-8'))
    if debug:
        harnessed_function_feedback = open(f"{output_dir}/debug-info/log_harnessed_funcs.txt", "w")
        harnessed_function_feedback.write("Unsuccessfully Harnessed Functions\n")
        for unharnessed_func in functions.getAllFunctions():
            if unharnessed_func.name not in argBuilder.harnessed_funcs:
                harnessed_function_feedback.write(f"{unharnessed_func.name}\n")
        harnessed_function_feedback.write("\nSuccessfully Harnessed Functions\n")
        for function in argBuilder.harnessed_funcs:
            harnessed_function_feedback.write(f"{function}\n")

    if os.path.exists(f"{input_dir}/seeds_validcp"):
        shutil.rmtree(f"{input_dir}/seeds_validcp")
    if os.path.exists(f"{input_dir}/seeds_invalidcp"):
        shutil.rmtree(f"{input_dir}/seeds_invalidcp")

def getBestHarnesses(compiler, heap, limit, final_corp=False):
    harnessesToGenerate = []
    currBitmap = compiler.globalBitmap.copy()
    count = 0
    totalHeap = len(heap)
    while count < min(totalHeap, limit):
        diff_dict = {} # dict that maps diff/coverage gain to list of sequences
        for sequence in heap:
            if sequence.uninteresting_setup:
                if final_corp:
                    continue # ignore non input-dependent harnesses in final set
                else:
                    diff_dict.setdefault(1, []).append(sequence)
                    continue # group all sequences with non-unique behavior together
            currDiff = len(sequence.bitmap.difference(currBitmap))
            diff_dict.setdefault(currDiff, []).append(sequence)
        if not len(diff_dict.keys()):
            print("WARNING: No harnesses with input-dependent coverage found")
            return heap
        max_diff = max(diff_dict.keys())
        if max_diff > 0:
            strongest_sequences = diff_dict[max_diff]
            if len(strongest_sequences) == totalHeap: # no sequences fully stand out, so just return a subset of them rather than just one
                for seq in strongest_sequences: # prioritize harnesses that use size arguments
                    if seq.uses_size_arg:
                        seq.effectiveness = max_diff
                        harnessesToGenerate.append(seq)
                if len(harnessesToGenerate):
                    return harnessesToGenerate
                for seq in random.sample(strongest_sequences, min(totalHeap, 5)):
                    seq.effectiveness = max_diff
                    harnessesToGenerate.append(seq)
                return harnessesToGenerate
            seq_to_add = strongest_sequences[0]
            for seq in strongest_sequences:
                for arg in seq.sequenceMembers[-1].args: # if the latest function call in the sequence does something with size, prioritize it more
                    if "size" in arg.value:
                        seq_to_add = seq
                        break
            seq_to_add.effectiveness = max_diff
            harnessesToGenerate.append(seq_to_add)
            currBitmap = currBitmap.union(seq_to_add.bitmap)
        else:
            break
        count += 1
    return harnessesToGenerate

def generateHarnesses(sequence, funcName):
    global argBuilder
    compiler.currIterSuccesses = []
    if sequence.functionCount < numfuncs:
        localSequences = []
        currentFunction = functions.getFunction(funcName)
        prevFunctionName = None
        sequence_functions = [mem.name for mem in sequence.sequenceMembers]
        for func in currentFunction.dependencies:
            if func.otherfunctionName != prevFunctionName:
                compiler.currIterSequences = dict()
            if not func.otherfunctionName in sequence_functions:
                harnesses = argBuilder.buildArguments(deepcopy(sequence), func, set())
                # temporarily store and update harnesses generated before optimization
                for harness in harnesses:
                    compiler.updateIterativeLogs(harness)
                localSequences += harnesses
                prevFunctionName = func.otherfunctionName
        bestHarnesses = getBestHarnesses(compiler, localSequences, 10)
        # refreshing stdout so everything previously written isn't overwritten
        if len(bestHarnesses):
            print("")
        for harness in bestHarnesses:
            compiler.globalBitmap = compiler.globalBitmap.union(harness.bitmap)
            compiler.updateDebugLogs(harness)
        if len(bestHarnesses):
            print("")
        for harness in bestHarnesses:
            generateHarnesses(harness, harness.sequenceMembers[-1].name)


def analyzeHarness(localsequence, heap, compiler):
    check = compiler.checkSequence(localsequence)
    if type(check) == set:
        if len(check.difference(compiler.globalBitmap)) > 0:
            localsequence.bitmap = check
            heap.append(localsequence)
            for func in localsequence.sequenceMembers:
                compiler.totalFunctions.add(func.name)
        else:
            compiler.failedCov += 1
            compiler.updateFailedFiles('''Function gains no additional coverage, likely because of
            outputs to the standard error or caught exceptions\n''', localsequence.cCode)
    else:
        compiler.updateFailedFiles(check, localsequence.cCode)

def process_config_file(filename):
    try:
        with open(filename, "r") as file:
            loaded_config = yaml.safe_load(file)
        check_blacklist = loaded_config.get("blacklist")
        blacklist = check_blacklist if check_blacklist and len(check_blacklist) else set()

        preamble_seq = loaded_config.get("preamble_seq") if "preamble_seq" in loaded_config else []

        check_arg_keys = loaded_config.get("arg_keys")
        arg_keys = check_arg_keys if check_arg_keys and len(check_arg_keys) else {}

        add_define_to_harness = loaded_config.get("add_define_to_harness") if "add_define_to_harness" in loaded_config else ""
    except:
        if filename:
            print("WARNING: Reading of config file failed")
        return set(), "", {}, ""

    return set(blacklist), preamble_seq, arg_keys, add_define_to_harness


def begin_harnessing_target(argBuilder, functions, compiler, init_sequences, target_function_name):
    routine_sequences = []
    uninteresting_sequences = []
    potential_setup = False
    target_function = functions.getFunction(target_function_name)
    if target_function:
        potential_setup = len(target_function.fuzz_args) > 0
    if len(preamble_seq) != 0:
        preamble_harnesses = call_preamble_sequence(preamble_seq)
        if not len(preamble_harnesses):
            print("WARNING: Preamble sequence had no successful invocations")
        else:
            print(f"Preamble sequence had {len(preamble_harnesses)} successful invocation(s)")
            init_sequences = preamble_harnesses

    # if targeted function is not a potential setup routine, then just move on
    if not potential_setup:
        print("Targeted function does not potentially consume fuzzer-generated data. Beginning to explore other setup routines")
        begin_harnessing(argBuilder, functions, compiler, init_sequences)
        return

    if len(preamble_seq) != 0:
        preamble_harnesses = call_preamble_sequence(preamble_seq)
        if not len(preamble_harnesses):
            print("WARNING: Preamble sequence had no successful invocations")
        else:
            print(f"Preamble sequence had {len(preamble_harnesses)} successful invocation(s)")
            init_sequences = preamble_harnesses

    # looping through the different restriction values
    for i in range(1, 4):
        if len(routine_sequences):
            break # once we're able to successfully call the target function, move on
        argBuilder.current_setup_restrictions = i
        for seq in init_sequences:
            if len(routine_sequences) and args.fast_mode:
                break
            compiler.currIterSequences = dict()
            currSequences = argBuilder.buildSetupFunction(deepcopy(seq), target_function_name, set())
            for s in currSequences:
                if s.uninteresting_setup:
                    uninteresting_sequences.append(s)
                else:
                    routine_sequences.append(s)
                    compiler.updateRoutineLogs(s)

    if not len(routine_sequences) and len(uninteresting_sequences):
        routine_sequences = uninteresting_sequences
        print("function successfully targeted, but had no input-dependent coverage, exploring functions that can be called after this")
    bestSequences = getBestHarnesses(compiler, routine_sequences, float("inf"))
    # resetting target sequences and successful sequences to only contain minimized harness corpus
    compiler.targetSequences = []
    compiler.successfulSequences = []
    open(f"{output_dir}/debug-info/log_setup_routines.txt", "w")
    if len(bestSequences):
        print("")
    for seq in bestSequences:
        compiler.globalBitmap = compiler.globalBitmap.union(seq.bitmap)
        compiler.finalizeRoutineLogs(seq)
    if len(bestSequences):
        print("")
    print("Beginning to explore functions that can be called after target function")

    for seq in bestSequences:
        seq.functionCount = 0
        seq.setupLen = len(seq.sequenceMembers)
        generateHarnesses(seq, seq.sequenceMembers[-1].name)

    # if targeted function is not a potential setup routine, then just move on
    print("Beginning to explore other setup routines")
    begin_harnessing(argBuilder, functions, compiler, init_sequences)

def call_preamble_sequence(preamble_sequences):
    current_sequences = [engine.Sequence()]
    for func in preamble_sequences:
        current_sequences = call_preamble(func, current_sequences)
    return current_sequences

def call_preamble(preamble_func, sequences):
    preamble_harnesses = []
    print(f"calling preamble for {preamble_func}")
    for seq in sequences:
        argBuilder.auxiliary_functions = {}
        currSequences = argBuilder.buildInitFunction(deepcopy(seq), preamble_func, set())
        for s in currSequences:
            preamble_harnesses.append(s)
    return preamble_harnesses


def begin_harnessing(argBuilder, functions, compiler, init_sequences):
    argBuilder.current_setup_restrictions = 1
    routine_sequences = []
    uninteresting_setup_routines = []
    if len(preamble_seq) != 0:
        preamble_harnesses = call_preamble_sequence(preamble_seq)
        if not len(preamble_harnesses):
            print("WARNING: Preamble sequence had no successful invocations")
        else:
            print(f"Preamble sequence had {len(preamble_harnesses)} successful invocation(s)")
            init_sequences = preamble_harnesses

    for seq in init_sequences:
        argBuilder.auxiliary_functions = {}
        if len(routine_sequences) and args.fast_mode:
            break
        for func in functions.setupFunctions:
            if func in preamble_seq:
                continue
            currSequences = argBuilder.buildSetupFunction(deepcopy(seq), func, set())
            for s in currSequences:
                if s.uninteresting_setup:
                    uninteresting_setup_routines.append(s)
                else:
                    routine_sequences.append(s)
                    compiler.updateRoutineLogs(s)

    if not compiler.func_targets and not len(routine_sequences):
        print("No successful setup routines detected using strict buffer types, moving onto relaxed types")
        argBuilder.current_setup_restrictions = 2 # change how we want to restrict the injection of fuzzing data, this allows (void*) casts
        for seq in init_sequences:
            argBuilder.auxiliary_functions = {}
            if len(routine_sequences) and args.fast_mode:
                break
            for func in functions.setupFunctions:
                if func in preamble_seq:
                    continue
                currSequences = argBuilder.buildSetupFunction(deepcopy(seq), func, set())
                for s in currSequences:
                    if s.uninteresting_setup:
                        uninteresting_setup_routines.append(s)
                    else:
                        routine_sequences.append(s)
                        compiler.updateRoutineLogs(s)

    if not compiler.func_targets and not len(routine_sequences):
        print("No successful setup routines detected using relaxed buffer types, moving onto exploring struct properties")
        argBuilder.current_setup_restrictions = 3 # change how we want to restrict the injection of fuzzing data, this allows struct property setting
        for seq in init_sequences:
            if len(routine_sequences) and args.fast_mode:
                break
            for func in functions.setupFunctions:
                currSequences = argBuilder.buildSetupFunction(deepcopy(seq), func, set())
                for s in currSequences:
                    if s.uninteresting_setup:
                        uninteresting_setup_routines.append(s)
                    else:
                        routine_sequences.append(s)
                        compiler.updateRoutineLogs(s)

            for func in functions.processingFunctions:
                currSequences = argBuilder.buildSetupFunction(deepcopy(seq), func, set())
                for s in currSequences:
                    if s.uninteresting_setup:
                        uninteresting_setup_routines.append(s)
                    else:
                        routine_sequences.append(s)
                        compiler.updateRoutineLogs(s)

    if not len(routine_sequences):
        if not len(uninteresting_setup_routines):
            print("No valid setup routines detected")
            exit()
        else:
            print("No setup routines with input-dependent coverage, further exploring function calls\n")
            routine_sequences = uninteresting_setup_routines

    bestSequences = getBestHarnesses(compiler, routine_sequences, float("inf"))
    if len(bestSequences):
        if not compiler.func_targets:
            open(f"{output_dir}/debug-info/log_setup_routines.txt", "w")
        # resetting target sequences and successful sequences to only contain minimized harness corpus
        print("")
        for seq in bestSequences:
            compiler.globalBitmap = compiler.globalBitmap.union(seq.bitmap)
            compiler.finalizeRoutineLogs(seq)
        compiler.sumRoutineLog()
        print("")
        print("Finished determining setup routines, moving onto additional function calls")
        for seq in bestSequences:
            seq.functionCount = 0
            seq.setupLen = len(seq.sequenceMembers)
            generateHarnesses(seq, seq.sequenceMembers[-1].name)

    print("finished harness generation, beginning edge optimization")
    compiler.currIterSuccesses = []
    exit_routine()

if __name__ == "__main__":
    signal.signal(signal.SIGINT, handle_interrupt)
    signal.signal(signal.SIGTERM, handle_interrupt)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--help", action="help", help="Show this help message and exit")
    parser.add_argument("--input", "-i", type=str, required=True, help="Path to directory housing the user-provided Makefile, both seeds_ dirs, and the Multiplier generated db file.")
    parser.add_argument("--output", "-o", type=str, required=True, help="Path to the output directory where OGHarn's artifacts will be stored.")
    parser.add_argument("--numfuncs", "-n", type=int, required=True, help="Maximum functions to call per harness following \"data entrypoint\" routines.")
    parser.add_argument("--mxdb", "-m", type=str, required=True, help="Path to Multiplier's generated .db database file.")
    parser.add_argument("--headers", "-h", nargs='+', action='append', required=True, help="Library headers to target, to be injected via #include in each harness.")
    parser.add_argument("--readhow", "-r", type=str, required=True, help="buf(b): Via buffer (e.g., foo(char* buffer)).\nfile (p): Via file name/path (e.g., bar(char* filename))\nfile pointer(fp): Via FILE* type.")
    parser.add_argument("--config", "-c", type=str, help="Path to optional config.yaml")
    parser.add_argument("--debug", "-d", action='store_true', help="Report the following information from the harnessing campaign:\n\tFailed harnesses and why they failed.\
                        \n\tSuccessfully-generated harnesses.\n\tInferred function-to-function dependencies.\n\tMultiplier-found declarations, typedef aliases, function pointers, enums, and macros.\
                        \n\tFunctions that were successfully harnessed.\n\tstatistics of the harness generation campaign.\n\tValues found from call-site tracking using Multiplier.")
    parser.add_argument("--execute_both", "-e", action='store_true', help="Run harnesses both dynamically/statically linked. Useful for linker-related crashes.")
    parser.add_argument("--recurse_headers", "-x", action='store_true', help="Recursively parse all headers. Useful if compiling needs extra dependencies.")
    parser.add_argument("--fast_mode", "-f", action='store_true', help="Work faster by disabling exhaustive arg search, keeping only the first-successful one.")
    parser.add_argument("--target_func", "-t", type=str, help="Attempt harnessing to reach only the specified function. Useful for targeted fuzzing.")
    parser.add_argument("--allow_pvalret", "-ap", action="store_true", help="Store function call site arguments as potential arguments during harnessing.")
    parser.add_argument("--allow_stderr", "-as", action='store_true', help="Keeps harnesses where stderr output seen. Useful if stderr is valid API behavior.")
    parser.add_argument("--allow_lincov", "-al", action='store_true', help="Keeps harnesses with linear codecov deltas. Useful for low input-dependent logic.")
    parser.add_argument("--allow_consts", "-ac", action='store_true', help="Considers const args from one function as potential non-const args for others.")
    parser.add_argument("--allow_deepaux", "-ad", action="store_true", help="Arg resolution via deeper auxiliary sequences. Adds significant cost to harnessing.")
    #setting default vals
    includes = ["<stdio.h>", "<stdarg.h>", "<string.h>", "<stdlib.h>", "<stdint.h>"]
    fuzzDataType = "CHARACTER_S"
    args = parser.parse_args()
    
    numfuncs = args.numfuncs

    if not args.headers[0]:
        print("Please supply the header files you want to explore")

    includes += ["<" + x + ">" for x in args.headers[0]]

    valid_readhow = args.readhow in ["b", "buf", "f", "file"]
    if not valid_readhow:
        print("WARNING: readhow argument not valid, exiting.")
        exit()

    read_from_buffer = True if args.readhow in ["b", "buf"] else False
    debug = args.debug
    track_params = args.allow_pvalret
    allow_stderr = args.allow_stderr
    allow_consts = args.allow_consts
    allow_lincov = args.allow_lincov
    allow_complex_aux_sequences = args.allow_deepaux 
        
    blacklist, preamble_seq, arg_keys, add_define_to_harness = process_config_file(args.config)
    
    try:
        input_dir = os.path.abspath(args.input)
    except Exception as e:
        print("WARNING: Failed to find the provided input directory, exiting.")
        exit()
    
    # get absolute path to output directory relative to to current working directory.
    output_dir = pathlib.Path(args.output).resolve()

    if os.path.isdir(output_dir):
        if os.listdir(output_dir) == ["gen"]: # if the only thing that exists in the output directory is gen, just get rid of it.
            shutil.rmtree(output_dir)
        else:
            overwrite = input("WARNING: The provided output directory already contains artifacts from a previous harness generation trial. Are you sure you want to overwrite this? (y/n)\n")
            if overwrite in ["y", "yes"]:
                shutil.rmtree(output_dir)
            else:
                print("Declined to overwrite output directory, exiting.")
                exit()
    
    index = process_mx.Index_Target_Header(args.mxdb, args.headers[0], args.recurse_headers)
    function_list, macros, enums, fps, aliases = index.extractArtifacts()
    print("Finished Indexing")
    comp_str_aliases = {}
    comp_mult_aliases = {}


    os.makedirs(f"{output_dir}/gen")

    compatibility = engine.CheckCompatibility(index.index, aliases, enums, args.target_func, track_params, allow_consts)

    functions = engine.APIfunctions()
    compatibility.process_functions(functions, function_list, blacklist)

    compatibility.checkrets(functions.getAllFunctions())

    dependencies = engine.BuildDependencies(functions, compatibility)
    dependencies.buildDependencies()

    if debug:
        os.mkdir(f"{output_dir}/debug-info")
        statFile = open(f"{output_dir}/debug-info/log_stats", "w")
        statFile.write("Minute, Total Harnesses, Successful, Failure on Compilation, Failure on Coverage, Failure on Crash, Total Edges, Total APIs\n")
        statFile.close()
        dump_definitions(functions, macros, enums, fps, aliases, compatibility)
        dump_dependencies(functions)
        if track_params:
            dump_potential_args(functions)
    print("Finished building dependencies")

    shutil.copytree(f"{input_dir}/seeds_valid", f"{input_dir}/seeds_validcp", dirs_exist_ok=True)
    shutil.copytree(f"{input_dir}/seeds_invalid", f"{input_dir}/seeds_invalidcp", dirs_exist_ok=True)

    compiler = engine.CompileHarness(input_dir, output_dir, functions, enums, includes, read_from_buffer, debug, compatibility, 
                                    allow_stderr, args.target_func, args.execute_both, allow_lincov, add_define_to_harness)
    argBuilder = harness_builder.Harness_Builder(functions, enums, macros, fps, compatibility,
                                                 compiler, args.target_func, arg_keys, args.fast_mode, allow_complex_aux_sequences)

    init_sequences = [engine.Sequence()]
    if not len(preamble_seq):
        for init_seq in functions.initFunctions():
            emptySeq = engine.Sequence()
            currSeq = argBuilder.buildInitFunction(deepcopy(emptySeq), init_seq, set())
            for s in currSeq:
                init_sequences.append(s)

    print("Finished determining initialization routines, moving onto setup routines")

    if args.target_func:
        begin_harnessing_target(argBuilder, functions, compiler, init_sequences, args.target_func)
    else:
        begin_harnessing(argBuilder, functions, compiler, init_sequences)
