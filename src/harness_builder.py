import itertools
from copy import deepcopy
import ogharn
import random
import multiplier as mx
from engine import (
    SequenceMember,
    literal_arg,
    function_pointer_arg,
    predefined_arg,
    define_new_val_arg,
    fuzz_buffer_arg,
    multiplier_type,
)


"""Builds the arguments for a function call in a sequence. This only initialized once at the beginning of the driver of the process."""


class Harness_Builder:
    def __init__(
        self,
        functions,
        enums,
        macros,
        functionPointers,
        compatibility,
        compiler,
        target_function,
        arg_keys,
        fast_mode,
        allow_complex_aux_sequences,
    ):
        self.functions = functions
        self.enums = enums
        self.macros = macros
        self.functionPointers = functionPointers
        self.compatibility = compatibility
        self.compiler = compiler
        self.target_function = target_function
        self.arg_keys = arg_keys
        self.fast_mode = fast_mode
        self.allow_complex_aux_sequences = allow_complex_aux_sequences

        # extra info
        self.macroVals = [0, 1, -1, 64]
        self.buffer_types = [
            "CHARACTER_S",
            "CHARACTER_U",
            "UINT",
            "VOID",
            "U_CHAR",
            "S_CHAR",
            "uintptr_t",
            "Bytef",
        ]
        self.auxiliary_functions = dict()
        self.harnessed_funcs = set()
        self.current_leaf_func = None
        self.current_setup_restrictions = 1
        self.last_called_func = ""
        self.current_dependency = None

    """Constructs the possible arguments that can be passed into a function"""

    def buildArguments(self, sequence, func, restricted_args):
        if not len(restricted_args):
            self.last_called_func = sequence.sequenceMembers[-1].name
            self.current_dependency = func
        currFunc = func.otherfunctionName
        currFunction = self.functions.getFunction(currFunc)
        priorityArgNum = func.currFunctionIndex
        macros = []

        possibleArgumentList = [[] for i in range(0, len(currFunction.mult_args))]

        argumentRelationships = self.checkArgumentRelationship(currFunction.mult_args)
        if priorityArgNum > -1:
            possibleArgumentList[priorityArgNum] += self.initializePriorityArg(
                sequence, func, priorityArgNum
            )

        argindex = 0
        for arg in currFunction.mult_args:
            if not argindex == priorityArgNum:
                possibleArgumentList[argindex] += self.checkFunctionValues(
                    sequence.sequenceMembers, arg, argindex in restricted_args
                )
                if (
                    arg.pointers or arg.typedef_pointers
                ) and argindex not in restricted_args:
                    possibleArgumentList[argindex].append(literal_arg("NULL"))
                macroList = self.checkMacros(arg)
                if macroList:
                    possibleArgumentList[argindex] += macroList
                    macros.append(argindex)
                possibleArgumentList[argindex] += self.checkEnums(arg)
            argindex += 1

        for i in range(0, len(possibleArgumentList)):
            if not i == priorityArgNum:
                if self.explore_auxiliary_function(
                    possibleArgumentList[i], currFunction.mult_args[i]
                ):
                    new_args = restricted_args.copy()
                    new_args.add(i)
                    self.current_leaf_func = (currFunc, "proc")
                    newAux = self.buildAuxiliaryVariables(
                        sequence, currFunction, i, new_args
                    )
                    interesting_seq = [
                        seq for seq in newAux if not seq.uninteresting_setup
                    ]
                    if len(interesting_seq):
                        return interesting_seq
                if i not in restricted_args:
                    possibleArgumentList[i].append(
                        self.define_new_value(
                            currFunction.mult_args[i], currFunc, sequence, i
                        )
                    )
                    if len(possibleArgumentList[i]):
                        ival = possibleArgumentList[i][0]
                        if isinstance(ival, predefined_arg):
                            if (
                                len(possibleArgumentList[i]) == 1
                                and ival.value == "fuzzData"
                                and i != priorityArgNum
                            ):
                                possibleArgumentList[i].append(
                                    self.define_new_value(
                                        currFunction.mult_args[i], currFunc, sequence, i
                                    )
                                )  # dest buffer
                                possibleArgumentList[i].append(literal_arg('"r"'))
                                possibleArgumentList[i].append(literal_arg('"w"'))
                                possibleArgumentList[i].append(
                                    literal_arg("fuzzData+size")
                                )
                            # if two arguments are the same value, explore just defining a new one
                            for j in range(0, len(possibleArgumentList)):
                                if j != i:
                                    if (
                                        len(possibleArgumentList[j]) == 1
                                        and len(possibleArgumentList[i]) == 1
                                    ):
                                        jval = possibleArgumentList[j][0]
                                        if isinstance(ival, predefined_arg):
                                            if jval.value == ival.value:
                                                if i != priorityArgNum:
                                                    possibleArgumentList[i].append(
                                                        self.define_new_value(
                                                            currFunction.mult_args[i],
                                                            currFunc,
                                                            sequence,
                                                            i,
                                                        )
                                                    )

        for i in range(0, len(currFunction.mult_args)):
            if not i == priorityArgNum and i not in restricted_args:
                possibleArgumentList[i] += list(
                    currFunction.potential_arguments[i]
                )  # adding any potential values derived from call site tracking
        self.updateFunctionCount(currFunction, sequence)
        return self.finalizePermutations(
            currFunction,
            sequence,
            possibleArgumentList,
            macros,
            argumentRelationships,
            priorityArgNum,
        )

    def buildAuxiliaryVariables(
        self,
        sequence,
        currFunction,
        argnum,
        restricted_indexes,
        aux_path=set(),
        depth=1,
    ):
        restricted_indexes = restricted_indexes.copy()
        init_leaf = self.current_leaf_func[1] == "init"
        # call a func that explores all reverse dependencies of arg num, check if "root" of call sequence is aux func
        if not self.check_aux_root(currFunction, argnum):
            return []
        function_calls = [mem.name for mem in sequence.sequenceMembers]
        argtype = currFunction.mult_args[argnum]
        possible_aux_function_calls = []
        possible_proc_calls = []
        funcTypeCodes = set()
        for dep in currFunction.reverseDependencies:
            otherfunc = self.functions.getFunction(dep.otherfunctionName)
            if (
                otherfunc.name in function_calls
                or otherfunc.name in aux_path
                or otherfunc.name == self.last_called_func
            ):
                # don't want to recursively try to call the same functions over again or create circular dependencies between functions
                continue
            if (otherfunc, dep.typeCode) not in funcTypeCodes:
                true_aux = otherfunc.category == "auxiliary"
                # returned value of function can be added as an argument to the current function
                if dep.typeCode == 2:
                    if val := self.compatibility.check_type_compatibility(
                        argtype, otherfunc.mult_ret, "dummyval", False
                    ):
                        if (
                            val.startswith("(void*)")
                            and not argtype.base_type == "VOID"
                        ):
                            continue
                        funcTypeCodes.add((otherfunc, dep.typeCode))
                        if true_aux:
                            possible_aux_function_calls.append(dep)
                        elif len(otherfunc.mult_args) == 1:
                            possible_proc_calls.append(dep)
                elif (
                    dep.typeCode == 3
                ):  # can also consider functions that are simple and easy to call
                    if val := self.compatibility.check_type_compatibility(
                        argtype,
                        otherfunc.mult_args[dep.currFunctionIndex],
                        "dummyval",
                        True,
                    ):
                        if (
                            val.startswith("(void*)")
                            and not argtype.base_type == "VOID"
                        ):
                            continue
                        if otherfunc.category == "auxiliary":
                            possible_aux_function_calls.append(dep)
                            funcTypeCodes.add((otherfunc, dep.typeCode))
                        elif (
                            len(otherfunc.mult_args) == 1
                        ):  # if the function isn't considered an auxiliary function, but has limited arguments, try calling it!
                            funcTypeCodes.add((otherfunc, dep.typeCode))
                            possible_proc_calls.append(dep)

        explore_further = (
            (not init_leaf) and depth < 4
        ) and self.allow_complex_aux_sequences

        # first attempt to call auxiliary functions
        final_sequences = self.call_auxiliary_func(
            possible_aux_function_calls,
            sequence,
            currFunction,
            restricted_indexes,
            aux_path,
            depth,
            explore_further,
        )

        if len(final_sequences) or not explore_further:
            return final_sequences

        # call other functions that are not auxiliary but are still potentially easy to call
        return self.call_auxiliary_func(
            possible_proc_calls,
            sequence,
            currFunction,
            restricted_indexes,
            aux_path,
            depth,
            False,
            True,
        )

    def check_aux_root(self, func, arg_index):
        function_queue = [(func, {arg_index}, 0)]
        visited = set()
        while len(function_queue):
            curr_func, arg_nums, depth = function_queue.pop(0)
            if depth > 4:
                continue
            visited.add(curr_func.name)
            for rev_dep in curr_func.reverseDependencies:
                if rev_dep.otherFunctionIndex in arg_nums:
                    next_dep = self.functions.getFunction(rev_dep.otherfunctionName)
                    true_aux = next_dep.category == "auxiliary"
                    if true_aux or len(next_dep.mult_args) == 1:
                        return True
                    if next_dep.name not in visited:
                        arg_index = 0
                        args_set = set()
                        for arg in next_dep.mult_args:
                            # grabbing only arg nums that are candidates for aux functions
                            builtin_type = arg.base_type in self.compatibility.type_map
                            if not builtin_type and self.explore_auxiliary_function(
                                [], arg
                            ):
                                args_set.add(arg_index)
                                arg_index += 1
                        if len(args_set):
                            function_queue.append((next_dep, args_set, depth + 1))
        return False

    def call_auxiliary_func(
        self,
        candidate_funcs,
        sequence,
        current_func,
        restricted_indexes,
        aux_path,
        depth,
        explore_further,
        pointer_arg=False,
    ):
        final_sequences = []
        previous_last_call = self.last_called_func
        for p in candidate_funcs:
            functions_called_in_sequence = {
                member.name for member in sequence.sequenceMembers
            }
            if p in functions_called_in_sequence:
                continue
            pointer_arg_num = p.currFunctionIndex if pointer_arg else -1
            if self.fast_mode and len(final_sequences):
                break
            if p.otherfunctionName not in self.auxiliary_functions:
                sequences = self.buildAuxiliaryFunction(
                    deepcopy(sequence),
                    p.otherfunctionName,
                    explore_further,
                    set(),
                    aux_path,
                    depth,
                    pointer_arg_num,
                )
                if not len(sequences):
                    self.auxiliary_functions[p.otherfunctionName] = []
                for seq in deepcopy(sequences):
                    if self.fast_mode and len(final_sequences):
                        break
                    # if the auxiliary function called didn't require another function call, save it
                    self.save_auxiliary_seq(seq)
                    if current_func.name == self.current_leaf_func[0]:
                        if self.current_leaf_func[1] == "setup":
                            final_sequences += self.buildSetupFunction(
                                seq, current_func.name, restricted_indexes
                            )
                        elif self.current_leaf_func[1] == "init":
                            final_sequences += self.buildInitFunction(
                                seq, current_func.name, restricted_indexes
                            )
                        else:
                            final_sequences += self.buildArguments(
                                seq, self.current_dependency, restricted_indexes
                            )
                    else:
                        final_sequences += self.buildAuxiliaryFunction(
                            seq,
                            current_func.name,
                            explore_further,
                            restricted_indexes,
                            aux_path,
                            depth,
                            -1,
                        )
                    self.last_called_func = previous_last_call
            else:
                # append successful auxiliary function calls to current sequence
                for aux_call in self.auxiliary_functions[p.otherfunctionName]:
                    if self.fast_mode and len(final_sequences):
                        break
                    new_seq = deepcopy(sequence)
                    new_seq.add_aux_calls(aux_call)
                    if current_func.name == self.current_leaf_func[0]:
                        if self.current_leaf_func[1] == "setup":
                            final_sequences += self.buildSetupFunction(
                                new_seq, current_func.name, restricted_indexes
                            )
                        elif self.current_leaf_func[1] == "init":
                            final_sequences += self.buildInitFunction(
                                new_seq, current_func.name, restricted_indexes
                            )
                        else:
                            final_sequences += self.buildArguments(
                                new_seq, self.current_dependency, restricted_indexes
                            )
                    else:
                        final_sequences += self.buildAuxiliaryFunction(
                            new_seq,
                            current_func.name,
                            True,
                            restricted_indexes,
                            aux_path,
                        )
                    self.last_called_func = previous_last_call
        return final_sequences

    def save_auxiliary_seq(self, sequence):
        aux_seq = []
        last_ref = sequence.sequenceMembers[-1].name
        for mem in reversed(sequence.sequenceMembers):
            aux_function_name = mem.name
            variables_to_init = []
            if aux_function_name in sequence.variablesToInitialize:
                for variable in sequence.variablesToInitialize[aux_function_name]:
                    variables_to_init.append(variable)
            hardcoded_values = []
            for var in sequence.hardCodedVariablesUsed:
                if aux_function_name + "var" in var:
                    hardcoded_values.append(sequence.hardCodedVariablesUsed[var])
            aux_seq.append((mem, variables_to_init, hardcoded_values))
        if not len(aux_seq):
            return
        if last_ref in self.auxiliary_functions:
            for saved in self.auxiliary_functions[last_ref]:
                if mem == saved[0]:
                    return
            self.auxiliary_functions[last_ref].append(list(reversed(aux_seq)))
        else:
            self.auxiliary_functions[last_ref] = [list(reversed(aux_seq))]

    # build the arguments for an auxiliary function call
    def buildAuxiliaryFunction(
        self,
        sequence,
        func,
        explore_further,
        restricted_args,
        aux_path,
        depth,
        pointer_arg_num,
    ):
        # depth allows us to track the current depth of auxiliary calls for the function of intereset. For example, if were building foo1 -> foo2 -> foo3 -> foo4, the depth is 4.
        aux_path = aux_path.copy()
        aux_path.add(func)
        depth += 1
        macros = []
        currFunction = self.functions.getFunction(func)

        possibleArgumentList = [[] for i in range(0, len(currFunction.mult_args))]

        if not len(currFunction.mult_args):
            seqMem = SequenceMember(currFunction.name, [])
            sequence.sequenceMembers.append(seqMem)
            heap = []
            ogharn.analyzeHarness(sequence, heap, self.compiler)
            if len(heap):
                self.harnessed_funcs.add(sequence.sequenceMembers[-1].name)
            return ogharn.getBestHarnesses(self.compiler, heap, 10)

        argindex = 0
        for arg in currFunction.mult_args:
            if (
                (arg.pointers or arg.typedef_pointers)
                and argindex not in restricted_args
                and argindex != pointer_arg_num
            ):
                possibleArgumentList[argindex].append(literal_arg("NULL"))
            possibleArgumentList[argindex] += self.checkFunctionValues(
                sequence.sequenceMembers, arg, argindex in restricted_args
            )
            macroList = self.checkMacros(arg)
            if macroList:
                possibleArgumentList[argindex] += macroList
                macros.append(argindex)
            possibleArgumentList[argindex] += self.checkEnums(arg)
            argindex += 1

        # add code for extra function tracing
        for i in range(0, len(possibleArgumentList)):
            builtin_type = (
                currFunction.mult_args[i].base_type in self.compatibility.type_map
            )
            # In order to further explore another function call to support the current function's argument, the argument should not be a builtin type and have no other candidate arguments
            if (
                explore_further
                and self.explore_auxiliary_function(
                    possibleArgumentList[i], currFunction.mult_args[i]
                )
                and not builtin_type
            ):
                new_args = restricted_args.copy()
                new_args.add(i)
                retSequence = self.buildAuxiliaryVariables(
                    sequence, currFunction, i, new_args, aux_path, depth
                )
                if len(retSequence):
                    return retSequence
            if i not in restricted_args:
                possibleArgumentList[i].append(
                    self.define_new_value(currFunction.mult_args[i], func, sequence, i)
                )

        for i in range(0, len(currFunction.mult_args)):
            if i not in restricted_args:
                possibleArgumentList[i] += list(
                    currFunction.potential_arguments[i]
                )  # adding any potential values derived from call site tracking

        self.updateFunctionCount(currFunction, sequence)
        return self.finalizePermutations(
            currFunction, sequence, possibleArgumentList, macros, [], -1
        )

    def buildInitFunction(self, sequence, func, restricted_args):
        macros = []
        currFunction = self.functions.getFunction(func)

        possibleArgumentList = [[] for i in range(0, len(currFunction.mult_args))]
        argumentRelationships = self.checkArgumentRelationship(currFunction.mult_args)

        argindex = 0
        for arg in currFunction.mult_args:
            possibleArgumentList[argindex] += self.checkFunctionValues(
                sequence.sequenceMembers, arg, argindex in restricted_args
            )
            if (
                arg.pointers or arg.typedef_pointers
            ) and argindex not in restricted_args:
                possibleArgumentList[argindex].append(literal_arg("NULL"))
            macroList = self.checkMacros(arg)
            if macroList:
                possibleArgumentList[argindex] += macroList
                macros.append(argindex)
            possibleArgumentList[argindex] += self.checkEnums(arg)
            argindex += 1

        for i in range(0, len(possibleArgumentList)):
            builtin_type = (
                currFunction.mult_args[i].base_type in self.compatibility.type_map
            )
            # In order to further explore another function call to support the current function's argument,
            # the argument should not be a builtin type and have no other candidate arguments
            if (
                self.explore_auxiliary_function(
                    possibleArgumentList[i], currFunction.mult_args[i]
                )
                and not builtin_type
            ):
                self.current_leaf_func = (func, "init")
                new_args = restricted_args.copy()
                new_args.add(i)
                retSequence = self.buildAuxiliaryVariables(
                    sequence, currFunction, i, new_args
                )
                if len(retSequence):
                    return retSequence

            if i not in restricted_args:
                possibleArgumentList[i].append(
                    self.define_new_value(currFunction.mult_args[i], func, sequence, i)
                )

        self.updateFunctionCount(currFunction, sequence)

        for i in range(0, len(currFunction.mult_args)):
            if i not in restricted_args:
                possibleArgumentList[i] += list(
                    currFunction.potential_arguments[i]
                )  # adding any potential values derived from call site tracking

        return self.finalizePermutations(
            currFunction,
            sequence,
            possibleArgumentList,
            macros,
            argumentRelationships,
            -1,
        )

    # builds the original setup function to pass fuzz data to
    def buildSetupFunction(self, sequence, func, restricted_args):
        if len(sequence.sequenceMembers):
            self.last_called_func = sequence.sequenceMembers[-1].name
        macros = []
        currFunction = self.functions.getFunction(func)

        possibleArgumentList = [[] for i in range(0, len(currFunction.mult_args))]
        argumentRelationships = self.checkArgumentRelationship(currFunction.mult_args)
        argindex = 0
        fuzzArguments = []
        for arg in currFunction.mult_args:
            if argindex in currFunction.fuzz_args:
                fuzz_arg = currFunction.fuzz_args[argindex]
                buf_arg = isinstance(fuzz_arg, fuzz_buffer_arg)
                if buf_arg:
                    if self.current_setup_restrictions == 1 and not fuzz_arg.void_cast:
                        fuzzArguments.append((argindex, predefined_arg(fuzz_arg.value)))
                    elif self.current_setup_restrictions == 2 and fuzz_arg.void_cast:
                        fuzzArguments.append((argindex, predefined_arg(fuzz_arg.value)))
                if self.current_setup_restrictions == 3 and not buf_arg:
                    for buf_prop in fuzz_arg.buf_props:
                        for size_prop in fuzz_arg.size_props:
                            new_def = self.define_new_fuzzing_value(
                                fuzz_arg.type,
                                buf_prop,
                                size_prop,
                                func,
                                sequence,
                                fuzz_arg.argnum,
                            )
                            fuzzArguments.append((argindex, new_def))

            if (
                arg.pointers or arg.typedef_pointers
            ) and argindex not in restricted_args:
                possibleArgumentList[argindex].append(literal_arg("NULL"))

            possibleArgumentList[argindex] += self.checkFunctionValues(
                sequence.sequenceMembers, arg, argindex in restricted_args
            )
            macroList = self.checkMacros(arg)
            if macroList:
                possibleArgumentList[argindex] += macroList
                macros.append(argindex)
            possibleArgumentList[argindex] += self.checkEnums(arg)
            argindex += 1
        totalSequences = []
        # gathering all permutations where fuzzData can be injected, limiting the possible arguments to only that value
        for val in fuzzArguments:
            currArgumentList = possibleArgumentList.copy()
            priorityArg = val[0]
            currArgumentList[priorityArg] = [val[1]]
            for i in range(0, len(currArgumentList)):
                curr_sequence = deepcopy(sequence)
                if i != priorityArg:
                    if self.explore_auxiliary_function(
                        possibleArgumentList[i], currFunction.mult_args[i]
                    ):
                        new_args = restricted_args.copy()
                        new_args.add(i)
                        self.current_leaf_func = (func, "setup")
                        retSequence = self.buildAuxiliaryVariables(
                            curr_sequence, currFunction, i, new_args
                        )
                        interesting_seq = [
                            seq for seq in retSequence if not seq.uninteresting_setup
                        ]
                        if len(interesting_seq):
                            return interesting_seq
                    if i not in restricted_args:
                        currArgumentList[i].append(
                            self.define_new_value(
                                currFunction.mult_args[i], func, curr_sequence, i
                            )
                        )
                    if (
                        currFunction.mult_args[i].base_type
                        in self.compatibility.buffer_types
                    ):
                        currArgumentList[i].append(
                            self.define_new_value(
                                currFunction.mult_args[i], func, curr_sequence, i
                            )
                        )
                        if currFunction.mult_args[i].pointers == 1:
                            currArgumentList[i].append(literal_arg('"r"'))
                            currArgumentList[i].append(literal_arg('"w"'))
                            currArgumentList[i].append(literal_arg("fuzzData+size"))

            for i in range(0, len(currFunction.mult_args)):
                if i != priorityArg and i not in restricted_args:
                    currArgumentList[i] += list(
                        currFunction.potential_arguments[i]
                    )  # adding any potential values derived from call site tracking

            self.updateFunctionCount(currFunction, curr_sequence)
            curr_sequence.fuzzDataUsed = True
            retstr = ""
            for arg in currArgumentList:
                retstr += "["
                for a in arg:
                    retstr += a.value + ","
                retstr += "]"
            totalSequences += self.finalizePermutations(
                currFunction,
                curr_sequence,
                currArgumentList,
                macros,
                argumentRelationships,
                -1,
            )
        return totalSequences

    def explore_auxiliary_function(self, arg_list, arg_type):
        # a bunch of checks to an argument to determine if we should explore calling an auxiliary function
        empty_list = not len(arg_list)
        only_nullptr = len(arg_list) == 1 and arg_list[0].value == "NULL"
        all_casts = (
            all(arg.value.startswith("(void*)") for arg in arg_list)
            and not arg_type.base_type == "VOID"
        )
        # we don't want to explore auxiliary functions for simple int arguments
        injectable = self.compatibility.check_builtin_type_compatibility(
            arg_type, "INT", "dummy"
        ) or self.compatibility.check_builtin_type_compatibility(
            arg_type, "size_t", "dummy"
        )
        # explore calling an auxiliary function if no other candidates exist and the argument is not simply an int
        return (empty_list or only_nullptr or all_casts) and not injectable

    # updates the number of times a function has been called, this is useful for variable naming
    def updateFunctionCount(self, currFunction, sequence):
        if currFunction.name not in sequence.functionsCalled:
            sequence.functionsCalled[currFunction.name] = 1
        else:
            sequence.functionsCalled[currFunction.name] += 1

    """Check what values from previous functions can be passed in as an argument"""

    def checkFunctionValues(self, sequence, currArg, restricted_arg):
        retlist = set()
        funcCount = dict()
        for seq in reversed(sequence):
            sequenceFunc = self.functions.getFunction(seq.name)
            if sequenceFunc.name not in funcCount:
                funcCount[sequenceFunc.name] = 1
            else:
                funcCount[sequenceFunc.name] += 1
            if compatible := self.compatibility.check_function_compatibility(
                [arg.value for arg in seq.args],
                currArg,
                sequenceFunc,
                funcCount[sequenceFunc.name],
            ):
                for val in compatible:
                    # some complicated checking for void* param types with auxiliary function call
                    if (
                        val.startswith("(void*)")
                        and not currArg.base_type == "VOID"
                        and restricted_arg
                    ):
                        continue
                    retlist.add(predefined_arg(val))
                if restricted_arg and len(retlist):
                    # ensures that only the value specially created for the current argument is considered
                    return list(retlist)
        return list(retlist)

    """Checks what constant values can be passed in as an argument"""

    def checkEnums(self, currArg):
        enums = []
        aliases = self.compatibility.get_aliases(currArg)
        for arg_type in aliases:
            if not isinstance(arg_type, str):
                arg_type = arg_type.base_type
            if arg_type in self.enums:
                for enum_val in self.enums[arg_type]:
                    enums.append(literal_arg(enum_val))
        return enums

    """Checks what macros be passed in as an argument"""

    def checkMacros(self, currArg):
        retlist = None
        if not currArg.pointers:
            if len(self.macros):
                retlist = []
                if self.compatibility.check_builtin_type_compatibility(
                    currArg, "INT", "dummy"
                ):
                    macros = random.choices(self.macros, k=10)
                    for m in macros:
                        retlist.append(literal_arg(m))
            elif self.compatibility.check_builtin_type_compatibility(
                currArg, "INT", "dummy"
            ):
                retlist = [literal_arg("0")]
        return retlist

    """Looks for a relationship between the arguments of a function"""

    def checkArgumentRelationship(self, arglist):
        argRelationships = []
        currDataStorage = -1
        argIndex = 0
        """assumptions we're making when checking for size relationships:
            *the data container will occur as a parameter before the size parameter
            *if there is some sort of data container as an argument, the next "size" argument will relate to this container
            In the end, this function just logs the argument indexes where the relationship occurs. This is added to the 
            arg relationships array in this way; (arg # of data container, arg # of size argument)"""
        for arg in arglist:
            # argument consumes buffer input
            if arg.consumes_fuzz[0] and not arg.consumes_fuzz[1]:
                currDataStorage = argIndex
            if (
                self.compatibility.check_builtin_type_compatibility(arg, "INT", "dummy")
                or self.compatibility.check_builtin_type_compatibility(
                    arg, "size_t", "dummy"
                )
                or self.compatibility.check_builtin_type_compatibility(
                    arg, "LONG", "dummy"
                )
            ):
                if currDataStorage > -1:
                    argRelationships.append((currDataStorage, argIndex))
                    currDataStorage = -1
            argIndex += 1
        return argRelationships

    """Builds the argument parameter that encapsulates data flow between function calls. This argument is the one that takes in a value previously modified by an earlier function"""

    def initializePriorityArg(self, sequence, func, priorityArgNum):
        priorityArg = []
        for member in reversed(sequence.sequenceMembers):
            if member.name == self.last_called_func:
                latestSequenceMember = member
                break

        currFunc = func.otherfunctionName
        currFunction = self.functions.getFunction(currFunc)
        argtype = currFunction.mult_args[priorityArgNum]
        # an argument of the previous function can be passed as an argument to the current function
        if func.typeCode == 3:
            otherArgIndex = func.otherFunctionIndex
            if not isinstance(latestSequenceMember.args[otherArgIndex], literal_arg):
                compatible = self.compatibility.check_type_compatibility(
                    argtype,
                    self.functions.getFunction(latestSequenceMember.name).mult_args[
                        otherArgIndex
                    ],
                    latestSequenceMember.args[otherArgIndex].value,
                    True,
                )
                priorityArg.append(predefined_arg(compatible))
        else:
            # the return type of a previous function can be passed as an argument to the current function
            variableName = (
                latestSequenceMember.name
                + "val"
                + str(sequence.functionsCalled[latestSequenceMember.name])
            )
            compatible = self.compatibility.check_type_compatibility(
                argtype,
                self.functions.getFunction(latestSequenceMember.name).mult_ret,
                variableName,
                False,
            )
            priorityArg.append(predefined_arg(compatible))
        return priorityArg

    def check_macros(
        self, macroCombinations, currFunc, sequence, currArgs, macros, argRelationships
    ):
        currentArgSequence = []
        for i in range(0, min(len(macroCombinations), 128)):
            currentArgSequence.append(
                self.replaceMacros(currArgs, macros, macroCombinations[i])
            )
        return currentArgSequence

    """Builds the final sequences for the function call."""

    def finalizePermutations(
        self,
        currFunc,
        sequence,
        possibleArguments,
        macros,
        argRelationships,
        priorityArg,
    ):
        heap = []
        totalPerms = 1
        macroCombinations = []
        if len(macros):
            macroCombinations = list(
                itertools.product(self.macroVals, repeat=len(macros))
            )
        currentArgSequence = []
        non_injectable_choices = []
        targetedFunc = self.target_function and (
            currFunc.name == self.target_function
            or currFunc.name.startswith(self.target_function + "overload")
        )

        for i in range(0, len(possibleArguments)):
            totalPerms *= len(possibleArguments[i])

        if totalPerms > 100:
            for i in range(0, 100):
                choices = [random.choice(sublist) for sublist in possibleArguments]
                regenAttempts = 0
                while choices in currentArgSequence and regenAttempts < 5:
                    choices = [random.choice(sublist) for sublist in possibleArguments]
                    regenAttempts += 1
                currentArgSequence.append(choices)
                non_injectable_args = [
                    i for i in range(0, len(choices)) if i not in macros
                ]
                if non_injectable_args not in non_injectable_choices:
                    currentArgSequence += self.check_macros(
                        macroCombinations,
                        currFunc,
                        sequence,
                        choices,
                        macros,
                        argRelationships,
                    )
                    non_injectable_choices.append(non_injectable_args)
        else:
            permutations = itertools.product(*possibleArguments)
            for perm in permutations:
                perm = list(perm)
                currentArgSequence.append(perm)
                non_injectable_args = [
                    i for i in range(0, len(perm)) if i not in macros
                ]
                if non_injectable_args not in non_injectable_choices:
                    currentArgSequence += self.check_macros(
                        macroCombinations,
                        currFunc,
                        sequence,
                        perm,
                        macros,
                        argRelationships,
                    )
                    non_injectable_choices.append(non_injectable_args)
        for arg in currentArgSequence:
            if currFunc.name in self.arg_keys:
                new_args = list(arg)
                for param in self.arg_keys[currFunc.name]:
                    index = param["index"]
                    value = param["value"]
                    new_args[int(index)] = literal_arg(value)
                arg = new_args
            sequences = self.finalizeArguments(
                currFunc, arg, argRelationships, priorityArg, deepcopy(sequence), True
            )
            for seq in sequences:
                # checking if fuzzData is in multiple argument slots, if it is, ignore it.
                latestMem = seq.sequenceMembers[-1]
                fuzzCount = 0
                for arg in latestMem.args:
                    if "fuzzData" in arg.value:
                        fuzzCount += 1
                    if arg.value == "size":
                        seq.uses_size_arg = (
                            True  # prioritize harnesses that use this size argument
                        )
                if fuzzCount > 1:
                    continue
                if targetedFunc:
                    seq.func_targeted = True
                latestMem = seq.sequenceMembers[-1]
                if currFunc.name in self.functions.auxiliaryFunctions:
                    ogharn.analyzeHarness(seq, heap, self.compiler)
                    if len(heap):
                        self.harnessed_funcs.add(seq.sequenceMembers[-1].name)
                    self.compiler.currIterSequences[str(seq.sequenceMembers)] = 1
                elif str(seq.sequenceMembers) not in self.compiler.currIterSequences:
                    ogharn.analyzeHarness(seq, heap, self.compiler)
                    if len(heap):
                        self.harnessed_funcs.add(seq.sequenceMembers[-1].name)
                    self.compiler.currIterSequences[str(seq.sequenceMembers)] = 1
        if currFunc.name in self.functions.auxiliaryFunctions:
            return heap
        return ogharn.getBestHarnesses(self.compiler, heap, float("inf"))

    def replaceMacros(self, args, macroIndexes, macroVals):
        macroCount = 0
        args = list(args)
        for i in range(0, len(args)):
            if macroCount < len(macroIndexes):
                if i == macroIndexes[macroCount]:
                    args[i] = literal_arg(str(macroVals[macroCount]))
                    macroCount += 1
        return tuple(args)

    def declare_fp(self, name, fp):
        call_res = multiplier_type()
        call_res = self.compatibility.init_mult_type(fp.call_result_type, call_res)
        declaration = f"static {self.compatibility.resolve_type(call_res)} {name}("
        for param in fp.parameter_types:
            mult_param = multiplier_type()
            mult_param = self.compatibility.init_mult_type(param, mult_param)
            declaration += self.compatibility.resolve_type(mult_param) + ", "
        declaration = declaration[:-2] + "){\n\texit(0);\n}"
        return declaration

    def define_new_fuzzing_value(
        self, arg_type, buf_field, size_field, func_name, sequence, arg_num
    ):
        sequence.initializeDictionaryMember(func_name)
        name = f"{func_name}var{arg_num}"
        decl = f"{self.compatibility.resolve_type(arg_type)} {name};\n"
        op = "."
        if arg_type.typedef_pointers:
            op = "->"
        if arg_type.pointers:
            decl = f"{self.compatibility.resolve_type(arg_type)[:-1]} {name};\n"
        mem = f"\t{name}{op}{buf_field[0]} = malloc(size);\n"
        var_init = decl + mem
        if isinstance(arg_type.internal_type, mx.ast.RecordType):
            var_init = "struct " + var_init
        setup = f"memcpy({name}{op}{buf_field[0]}, fuzzData, size);\n"
        if size_field:
            setup += f"{name}{op}{size_field[0]} = {self.compatibility.check_builtin_type_compatibility(size_field[1], "INT", "size")};"
        definition = var_init + setup
        if arg_type.pointers:
            return define_new_val_arg(
                f"&{func_name}var{arg_num}", definition, f"{func_name}var{arg_num}"
            )
        else:
            return define_new_val_arg(
                f"{func_name}var{arg_num}", definition, f"{func_name}var{arg_num}"
            )

    def define_new_value(self, arg_type, func_name, sequence, arg_num):
        sequence.initializeDictionaryMember(func_name)
        aliases = self.compatibility.get_aliases(arg_type)
        headerfuncPointer = (
            False  # function pointer explicitly declared in header file with name
        )
        argFuncPointer = (
            False  # function pointer declared inline of function definition
        )
        for a in aliases:
            if type(a) is not str and a.base_type in self.functionPointers:
                headerfuncPointer = True
                arg_type = a
                break
            elif type(a) is not str and a.base_type.startswith("function_pointer"):
                argFuncPointer = True
                arg_type = a
                break

        if headerfuncPointer:
            return function_pointer_arg(
                arg_type.base_type + "fp",
                self.declare_fp(
                    arg_type.base_type + "fp", self.functionPointers[arg_type.base_type]
                ),
            )
        elif argFuncPointer:
            return function_pointer_arg(
                arg_type.base_type + "fp",
                self.declare_fp(arg_type.base_type + "fp", arg_type.internal_type),
            )
        if arg_type.pointers and arg_type.base_type not in self.buffer_types:
            return define_new_val_arg(
                f"&{func_name}var{arg_num}", None, f"{func_name}var{arg_num}"
            )
        else:
            return define_new_val_arg(
                f"{func_name}var{arg_num}", None, f"{func_name}var{arg_num}"
            )

    """Creates new variables for a specific function call"""

    def initializeVariables(self, currFunction, arg, currSequence):
        currSequence.functionCount += 1
        arg = list(arg)
        argIndex = 0
        currSequence.initializeDictionaryMember(currFunction.name)
        for args in arg:
            if isinstance(args, function_pointer_arg):
                currSequence.functionPointerDeclarations[args.value] = args.definition
            elif isinstance(args, define_new_val_arg):
                curr_arg = currFunction.mult_args[argIndex]
                resolved_type = self.compatibility.resolve_type(curr_arg)
                if isinstance(curr_arg.internal_type, mx.ast.RecordType):
                    resolved_type = "struct " + resolved_type
                if curr_arg.pointers and curr_arg.base_type not in self.buffer_types:
                    currSequence.variablesToInitialize[currFunction.name].append(
                        (resolved_type[:-1], args.definition, args.name)
                    )
                else:
                    currSequence.variablesToInitialize[currFunction.name].append(
                        (resolved_type, args.definition, args.name)
                    )
            argIndex += 1
        currSequence.sequenceMembers.append(
            SequenceMember(currFunction.name, tuple(arg))
        )
        return currSequence

    """Recognizes the relationship between arguments and modifies those arguments according to their relationship."""

    def finalizeArguments(
        self, currFunc, arg, argrelationships, priorityArg, currSequence, macros
    ):
        relationShipArg = []
        for args in arg:
            relationShipArg.append(args)
        relationshipAdded = False
        finalRelationShipSequences = []
        relationshipPerms = []
        indexList = []
        indexList.extend(range(0, len(argrelationships)))
        for i in range(0, len(argrelationships)):
            relationshipPerms += list(itertools.combinations(indexList, r=i + 1))
        for relPerm in relationshipPerms:
            relArg = relationShipArg.copy()
            for index in relPerm:
                relationship = argrelationships[index]
                if not relationship[1] == priorityArg:
                    relationshipAdded = True
                    # no matter what the argument was, we're rewriting it to be a size argument
                    relArg[relationship[1]] = literal_arg("placeholder")
            newSeq = self.initializeVariables(
                currFunc, tuple(relArg), deepcopy(currSequence)
            )
            arguments = list(newSeq.sequenceMembers[-1].args)
            for index in relPerm:
                relationship = argrelationships[index]
                currArg = newSeq.sequenceMembers[-1].args[relationship[0]].value
                if not relationship[1] == priorityArg:
                    mult_size_type = currFunc.mult_args[relationship[1]]
                    mult_buf_type = currFunc.mult_args[relationship[0]]
                    if mult_size_type.pointers:
                        arg_val = None
                        if (
                            "fuzzData" in arguments[relationship[0]].value
                            and self.compiler.read_from_buffer
                        ):
                            arg_val = "size"
                        else:
                            arg_val = f"sizeof({arguments[relationship[0]].value.strip("*").strip("&")})"
                        newSeq.initializeDictionaryMember(currFunc.name)
                        new_arg = (
                            currFunc.name + "var" + mult_size_type.base_type + "size"
                        )
                        define_new_arg = define_new_val_arg(
                            "&" + new_arg,
                            f"{self.compatibility.resolve_type(currFunc.mult_args[relationship[1]])[:-1]} {new_arg} = {arg_val};",
                            new_arg,
                        )
                        arguments[relationship[1]] = define_new_arg
                        newSeq.variablesToInitialize[currFunc.name].append(
                            (
                                self.compatibility.resolve_type(
                                    currFunc.mult_args[relationship[1]]
                                )[:-1],
                                define_new_arg.definition,
                                define_new_arg.name,
                            )
                        )
                    elif (
                        mult_buf_type.consumes_fuzz[0]
                        and not mult_buf_type.consumes_fuzz[1]
                    ) and not arguments[relationship[0]].value == "NULL":
                        if (
                            "fuzzData" in arguments[relationship[0]].value
                            and self.compiler.read_from_buffer
                        ):
                            arguments[relationship[1]] = predefined_arg("size")
                        elif (
                            mult_buf_type.base_type == "VOID"
                            and "fuzzData" in arguments[relationship[0]].value
                        ):
                            arguments[relationship[1]] = literal_arg(
                                "strlen(" + currArg[7:].strip("*").strip("&") + ")"
                            )
                        elif mult_buf_type.base_type == "VOID":
                            arguments[relationship[1]] = literal_arg(
                                "sizeof(" + currArg[7:].strip("*").strip("&") + ")"
                            )
                        else:
                            arguments[relationship[1]] = literal_arg(
                                "sizeof(" + currArg.strip("*").strip("&") + ")"
                            )
                    else:
                        arguments[relationship[1]] = literal_arg(
                            "sizeof(" + currArg.strip("*").strip("&") + ")"
                        )
            newSeq.sequenceMembers[-1].args = arguments
            finalRelationShipSequences.append(newSeq)
        if relationshipAdded and not macros:
            return finalRelationShipSequences
        else:
            finalRelationShipSequences.append(
                self.initializeVariables(currFunc, tuple(arg), currSequence)
            )
            return finalRelationShipSequences
